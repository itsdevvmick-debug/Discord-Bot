import sys
from types import SimpleNamespace

sys.path.insert(0, '67')

from cogs import store as store_module
from cogs import tickets as tickets_module


def test_stripe_button_is_available_when_global_stripe_is_configured():
    product = {'stripe_url': ''}

    assert store_module.should_show_stripe_button(product, stripe_configured=True)


def test_panel_permission_allows_admins_and_owner():
    guild = SimpleNamespace(owner_id=123)
    user = SimpleNamespace(
        id=456,
        roles=[],
        guild_permissions=SimpleNamespace(administrator=True, manage_guild=True, manage_channels=False),
    )

    assert tickets_module.can_manage_ticket_panel(user, guild, role_id=999)
