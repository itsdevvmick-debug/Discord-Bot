"""
Store Cog - product storefront with multi-forum posting

Features implemented:
- /newproduct to create a product and post it to a selected channel
- Posts include interactive Robux and Stripe purchase buttons when enabled
- Robux confirmation queue entry
- Stripe session creation (via stripe library if configured) and webhook-compatible metadata
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import Config
from database import db

logger = logging.getLogger(__name__)


def should_show_stripe_button(product: object | None = None, stripe_configured: bool | None = None) -> bool:
    """Return True when Stripe checkout is available for a product or globally configured."""
    if stripe_configured is None:
        stripe_configured = bool(Config.STRIPE_API_KEY)

    if stripe_configured:
        return True

    if product is None:
        return False

    if isinstance(product, dict):
        stripe_url = product.get("stripe_url") or ""
    else:
        stripe_url = getattr(product, "stripe_url", "") or ""

    return bool(stripe_url)


class RobuxBuyView(discord.ui.View):
    def __init__(self, product_id: int, stripe_available: bool = False):
        super().__init__(timeout=None)
        self.product_id = product_id
        # Robux button
        btn = discord.ui.Button(style=discord.ButtonStyle.primary, label="Buy with Robux", custom_id=f"robux:{product_id}")
        btn.callback = self._on_robux_buy
        self.add_item(btn)

        # Optional Stripe button that creates a checkout session for the clicking user
        if stripe_available:
            sbtn = discord.ui.Button(style=discord.ButtonStyle.success, label="Pay with Stripe", custom_id=f"stripe:{product_id}")
            sbtn.callback = self._on_stripe_buy
            self.add_item(sbtn)

    async def _on_robux_buy(self, interaction: discord.Interaction):
        try:
            product = await db.fetch_product_by_id(self.product_id)
            if not product:
                await interaction.response.send_message("Product not found.", ephemeral=True)
                return

            confirm_view = ConfirmRobuxView(self.product_id)
            await interaction.response.send_message(
                "To purchase with Robux: follow the Robux link in the forum post, complete the purchase on Roblox, then press Confirm below when done. A staff member will verify the purchase.",
                view=confirm_view,
                ephemeral=True,
            )
        except Exception:
            logger.exception("Error handling robux buy")
            await interaction.response.send_message("Failed to start Robux purchase flow.", ephemeral=True)

    async def _on_stripe_buy(self, interaction: discord.Interaction):
        try:
            product = await db.fetch_product_by_id(self.product_id)
            if not product:
                await interaction.response.send_message("Product not found.", ephemeral=True)
                return

            direct_checkout_url = None
            if isinstance(product, dict):
                direct_checkout_url = product.get('stripe_url') or None
            else:
                direct_checkout_url = getattr(product, 'stripe_url', None) or None

            if direct_checkout_url:
                await interaction.response.send_message(f"Open this checkout page to pay: {direct_checkout_url}", ephemeral=True)
                return

            if Config.STRIPE_API_KEY:
                try:
                    import stripe

                    stripe.api_key = Config.STRIPE_API_KEY
                    price = float(product['price'] or 0)
                    session = stripe.checkout.Session.create(
                        payment_method_types=['card'],
                        line_items=[{
                            'price_data': {
                                'currency': 'usd',
                                'product_data': {'name': product['name']},
                                'unit_amount': int(price * 100),
                            },
                            'quantity': 1,
                        }],
                        mode='payment',
                        success_url=Config.STRIPE_SUCCESS_URL,
                        cancel_url=Config.STRIPE_CANCEL_URL,
                        metadata={'product_id': str(self.product_id), 'discord_user_id': str(interaction.user.id)},
                    )

                    await interaction.response.send_message(f"Open this checkout page to pay: {session.url}", ephemeral=True)
                    return
                except Exception:
                    logger.exception("Stripe checkout session creation failed")

            checkout_url = f"{Config.BASE_URL}/create-checkout?product_id={self.product_id}&user_id={interaction.user.id}"
            await interaction.response.send_message(f"Open this checkout page to pay: {checkout_url}", ephemeral=True)

        except Exception:
            logger.exception("Error creating stripe checkout")
            await interaction.response.send_message("Failed to create checkout session.", ephemeral=True)


class ConfirmRobuxView(discord.ui.View):
    def __init__(self, product_id: int):
        super().__init__(timeout=60)
        self.product_id = product_id

    @discord.ui.button(label="Confirm Purchase", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await db.add_robux_verification(self.product_id, interaction.user.id, None, None)
            if Config.PARTNER_LOGS_CHANNEL_ID:
                channel = interaction.client.get_channel(Config.PARTNER_LOGS_CHANNEL_ID)
                if channel:
                    await channel.send(f"Robux purchase pending verification: user={interaction.user.mention} product_id={self.product_id}")

            await interaction.response.edit_message(content="Thanks — your purchase is queued for staff verification.", view=None)
        except Exception:
            logger.exception("Error confirming robux purchase")
            await interaction.response.send_message("Failed to queue verification.", ephemeral=True)


class StoreCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.stripe_enabled = bool(Config.STRIPE_API_KEY)

    @app_commands.command(name="newproduct", description="Create a new product and post it to a channel")
    @app_commands.describe(
        channel="Channel where the product should be posted",
        name="Product name",
        description="Product description",
        price="Price (optional)",
        stripe_url="Stripe checkout URL (optional)",
        robux_url="Roblox item URL (optional)",
        delivery_content="Delivery content for the buyer",
        image_url="Image URL (optional)",
        thumbnail_url="Thumbnail URL (optional)",
        tags="Tags (optional)",
        category="Category (optional)",
    )
    async def newproduct(
        self,
        interaction: discord.Interaction,
        channel: discord.abc.GuildChannel,
        name: str,
        description: str,
        price: Optional[float] = None,
        stripe_url: Optional[str] = None,
        robux_url: Optional[str] = None,
        delivery_content: str = "",
        image_url: Optional[str] = None,
        thumbnail_url: Optional[str] = None,
        tags: Optional[str] = None,
        category: Optional[str] = None,
    ):
        # Permissions
        allowed = False
        try:
            pm_role_id = getattr(Config, 'PRODUCT_MANAGER_ROLE_ID', 0)
            if pm_role_id and any(r.id == pm_role_id for r in interaction.user.roles):
                allowed = True
        except Exception:
            allowed = False

        if not allowed and not (interaction.user.guild_permissions.manage_guild or interaction.user.guild_permissions.administrator):
            await interaction.response.send_message("You don't have permission to add products.", ephemeral=True)
            return

        if not hasattr(channel, 'send'):
            await interaction.response.send_message(
                "Selected channel cannot receive product posts. Please choose a text or forum channel.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            channel_ids = [channel.id]

            product_id = await db.create_product(
                name=name,
                description=description,
                price=price or 0.0,
                stripe_url=stripe_url or '',
                robux_url=robux_url or '',
                delivery_content=delivery_content or '',
                image_url=image_url or '',
                thumbnail_url=thumbnail_url or '',
                forum_channel_ids=','.join(str(x) for x in channel_ids),
                message_ids='',
                creator_id=interaction.user.id,
                tags=tags or '',
                category=category or '',
            )

            embed = discord.Embed(title=name, description=description or "", color=discord.Color.blue())
            if image_url:
                embed.set_image(url=image_url)
            if thumbnail_url:
                embed.set_thumbnail(url=thumbnail_url)
            embed.add_field(name="Price", value=f"{price or 0}")
            methods = []
            if stripe_url or Config.STRIPE_API_KEY:
                methods.append("Stripe")
            if robux_url:
                methods.append("Robux")
            embed.add_field(name="Payment Methods", value=", ".join(methods) or "None", inline=False)
            embed.set_footer(text=f"Product ID: {product_id}")

            message_map = {}
            for cid in channel_ids:
                post_channel = self.bot.get_channel(cid) or await self.bot.fetch_channel(cid)
                if not post_channel or not hasattr(post_channel, 'send'):
                    logger.warning("Channel %s not found or cannot send messages, skipping", cid)
                    continue

                view = RobuxBuyView(product_id, stripe_available=should_show_stripe_button(product={"stripe_url": stripe_url or ""}, stripe_configured=bool(Config.STRIPE_API_KEY)))

                sent = await post_channel.send(embed=embed, view=view)
                message_map[str(cid)] = sent.id

            await db.update_product_message_ids(product_id, json.dumps(message_map))

            # Register persistent views
            self.bot.add_view(RobuxBuyView(product_id, stripe_available=should_show_stripe_button(product={"stripe_url": stripe_url or ""}, stripe_configured=bool(Config.STRIPE_API_KEY))))

            await interaction.followup.send(f"Product created with ID {product_id} and posted to {len(message_map)} channel(s).", ephemeral=True)

        except Exception as exc:
            logger.exception("Failed to add product: %s", exc)
            await interaction.followup.send("Failed to create product.", ephemeral=True)

    @app_commands.command(name='products', description='List all products')
    async def products(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            prods = await db.fetch_all_products()
            if not prods:
                await interaction.followup.send('No products found.', ephemeral=True)
                return

            lines = []
            for p in prods:
                pid = p['id'] if isinstance(p, dict) else p[0]
                name = p['name'] if isinstance(p, dict) else p[1]
                price = p['price'] if isinstance(p, dict) else p[3]
                lines.append(f"{pid}: {name} — {price}")

            await interaction.followup.send('\n'.join(lines), ephemeral=True)
        except Exception:
            logger.exception('Failed to list products')
            await interaction.followup.send('Failed to list products.', ephemeral=True)

    @app_commands.command(name='productinfo', description='Show product details')
    @app_commands.describe(product_id='Product ID')
    async def productinfo(self, interaction: discord.Interaction, product_id: int):
        await interaction.response.defer(ephemeral=True)
        try:
            p = await db.fetch_product_by_id(product_id)
            if not p:
                await interaction.followup.send('Product not found.', ephemeral=True)
                return
            # Build embed
            embed = discord.Embed(title=p['name'], description=p['description'] or '')
            embed.add_field(name='Price', value=str(p['price']))
            embed.add_field(name='Stripe URL', value=p['stripe_url'] or '—', inline=False)
            embed.add_field(name='Robux URL', value=p['robux_url'] or '—', inline=False)
            embed.add_field(name='Purchase Count', value=str(p['purchase_count']))
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception:
            logger.exception('Failed to get product info')
            await interaction.followup.send('Failed to get product info.', ephemeral=True)

    @app_commands.command(name='productdelete', description='Delete a product and remove forum posts')
    @app_commands.describe(product_id='Product ID')
    async def productdelete(self, interaction: discord.Interaction, product_id: int):
        # permission check
        if not (interaction.user.guild_permissions.manage_guild or interaction.user.guild_permissions.administrator or any(r.id == getattr(Config, 'PRODUCT_MANAGER_ROLE_ID', 0) for r in interaction.user.roles)):
            await interaction.response.send_message('You do not have permission to delete products.', ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            p = await db.fetch_product_by_id(product_id)
            if not p:
                await interaction.followup.send('Product not found.', ephemeral=True)
                return

            # delete forum messages
            try:
                msg_map = json.loads(p['message_ids'] or '{}')
                for cid, mid in msg_map.items():
                    try:
                        ch = self.bot.get_channel(int(cid)) or await self.bot.fetch_channel(int(cid))
                        msg = await ch.fetch_message(int(mid))
                        await msg.delete()
                    except Exception:
                        continue
            except Exception:
                logger.exception('Failed removing forum messages')

            await db.delete_product(product_id)
            await interaction.followup.send('Product deleted and posts removed.', ephemeral=True)
        except Exception:
            logger.exception('Failed to delete product')
            await interaction.followup.send('Failed to delete product.', ephemeral=True)

    @app_commands.command(name='productedit', description='Edit product fields')
    @app_commands.describe(product_id='Product ID', name='Name', description='Description', price='Price', stripe_url='Stripe URL', robux_url='Roblox URL', delivery_content='Delivery content')
    async def productedit(self, interaction: discord.Interaction, product_id: int, name: Optional[str] = None, description: Optional[str] = None, price: Optional[float] = None, stripe_url: Optional[str] = None, robux_url: Optional[str] = None, delivery_content: Optional[str] = None):
        # permission check
        if not (interaction.user.guild_permissions.manage_guild or interaction.user.guild_permissions.administrator or any(r.id == getattr(Config, 'PRODUCT_MANAGER_ROLE_ID', 0) for r in interaction.user.roles)):
            await interaction.response.send_message('You do not have permission to edit products.', ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            p = await db.fetch_product_by_id(product_id)
            if not p:
                await interaction.followup.send('Product not found.', ephemeral=True)
                return

            updates = {}
            if name is not None:
                updates['name'] = name
            if description is not None:
                updates['description'] = description
            if price is not None:
                updates['price'] = price
            if stripe_url is not None:
                updates['stripe_url'] = stripe_url
            if robux_url is not None:
                updates['robux_url'] = robux_url
            if delivery_content is not None:
                updates['delivery_content'] = delivery_content
            # stock is optional
            # try to parse a 'stock' keyword in description or provide a dedicated command

            if updates:
                await db.update_product(product_id, **updates)

                # update existing forum posts
                try:
                    msg_map = json.loads(p['message_ids'] or '{}')
                    for cid, mid in msg_map.items():
                        try:
                            ch = self.bot.get_channel(int(cid)) or await self.bot.fetch_channel(int(cid))
                            msg = await ch.fetch_message(int(mid))
                            embed = discord.Embed(title=updates.get('name', p['name']), description=updates.get('description', p['description']))
                            embed.add_field(name='Price', value=str(updates.get('price', p['price'])))
                            methods = []
                            if updates.get('stripe_url', p['stripe_url']) or Config.STRIPE_API_KEY:
                                methods.append('Stripe')
                            if updates.get('robux_url', p['robux_url']):
                                methods.append('Robux')
                            embed.add_field(name='Payment Methods', value=', '.join(methods) or 'None', inline=False)
                            await msg.edit(embed=embed)
                        except Exception:
                            continue
                except Exception:
                    logger.exception('Failed to update forum posts')

                await interaction.followup.send('Product updated and posts refreshed.', ephemeral=True)
            else:
                await interaction.followup.send('No changes provided.', ephemeral=True)
        except Exception:
            logger.exception('Failed to edit product')
            await interaction.followup.send('Failed to edit product.', ephemeral=True)

    @app_commands.command(name='productstock', description='Show product stock')
    @app_commands.describe(product_id='Product ID')
    async def productstock(self, interaction: discord.Interaction, product_id: int):
        await interaction.response.defer(ephemeral=True)
        try:
            p = await db.fetch_product_by_id(product_id)
            if not p:
                await interaction.followup.send('Product not found.', ephemeral=True)
                return
            stock = p.get('stock') if isinstance(p, dict) else (p[3] if len(p) > 3 else None)
            await interaction.followup.send(f"Product {product_id} stock: {stock}", ephemeral=True)
        except Exception:
            logger.exception('Failed to get product stock')
            await interaction.followup.send('Failed to get product stock.', ephemeral=True)

    @app_commands.command(name='productstockset', description='Set product stock (managers only)')
    @app_commands.describe(product_id='Product ID', amount='Stock amount (use -1 for unlimited)')
    async def productstockset(self, interaction: discord.Interaction, product_id: int, amount: int):
        if not (interaction.user.guild_permissions.manage_guild or interaction.user.guild_permissions.administrator or any(r.id == getattr(Config, 'PRODUCT_MANAGER_ROLE_ID', 0) for r in interaction.user.roles)):
            await interaction.response.send_message('You do not have permission to set stock.', ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            await db.update_product(product_id, stock=amount)
            await interaction.followup.send(f'Stock for product {product_id} set to {amount}.', ephemeral=True)
        except Exception:
            logger.exception('Failed to set product stock')
            await interaction.followup.send('Failed to set product stock.', ephemeral=True)

    @app_commands.command(name='stripeverify', description='Verify a Stripe session id to deliver product manually')
    @app_commands.describe(session_id='Stripe Checkout Session ID')
    async def stripeverify(self, interaction: discord.Interaction, session_id: str):
        if not self.stripe_enabled:
            await interaction.response.send_message('Stripe is not configured.', ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            import stripe
            stripe.api_key = Config.STRIPE_API_KEY
            session = stripe.checkout.Session.retrieve(session_id)
            metadata = session.get('metadata', {}) or {}
            product_id = metadata.get('product_id')
            discord_user = metadata.get('discord_user_id') or str(interaction.user.id)
            transaction_id = session.get('payment_intent') or session.get('id')

            await db.add_purchase(int(product_id), int(discord_user), 'stripe', transaction_id, 'completed')
            await db.increment_product_purchase_count(int(product_id))

            # Deliver product via DM
            await self.deliver_product_to_user(int(product_id), int(discord_user), transaction_id, 'stripe')

            await interaction.followup.send('Session verified and product delivered (if possible).', ephemeral=True)
        except Exception as exc:
            logger.exception('Stripe verify failed: %s', exc)
            await interaction.followup.send('Failed to verify session.', ephemeral=True)

    async def deliver_product_to_user(self, product_id: int, user_id: int, transaction_id: str, payment_method: str):
        try:
            product = await db.fetch_product_by_id(product_id)
            if not product:
                return False

            content = product['delivery_content']
            name = product['name']

            user = await self.bot.fetch_user(user_id)
            if not user:
                return False

            try:
                await user.send(f"Thanks for your purchase of **{name}**!\n\n{content}")
            except discord.Forbidden:
                # DMs disabled — log
                if Config.LOGS_CHANNEL_ID:
                    ch = self.bot.get_channel(Config.LOGS_CHANNEL_ID) or await self.bot.fetch_channel(Config.LOGS_CHANNEL_ID)
                    if ch:
                        await ch.send(f"Failed to DM user {user} for product {product_id}. DMs disabled.")
                return False

            # record delivery
            await db.mark_purchase_delivered_by_tx(transaction_id)
            await db.increment_product_purchase_count(product_id)

            # log
            if Config.LOGS_CHANNEL_ID:
                ch = self.bot.get_channel(Config.LOGS_CHANNEL_ID) or await self.bot.fetch_channel(Config.LOGS_CHANNEL_ID)
                if ch:
                    await ch.send(f"Delivered product {product_id} to {user} via {payment_method}. Transaction {transaction_id}")

            return True
        except Exception:
            logger.exception('Failed to deliver product')
            return False


async def setup(bot: commands.Bot):
    cog = StoreCog(bot)
    await bot.add_cog(cog)

    # Register persistent views for existing products
    try:
        products = await db.fetch_all_products()
        for p in products:
            pid = int(p['id']) if isinstance(p, dict) else p[0]
            bot.add_view(RobuxBuyView(pid, stripe_available=should_show_stripe_button(product=p, stripe_configured=bool(Config.STRIPE_API_KEY))))
    except Exception:
        pass
