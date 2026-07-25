"""
Database module for storing persistent data
"""
import aiosqlite
import os
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def _sqlite_url_to_path(value: str | None, default: str = "bot_database.db") -> str:
    if not value:
        return default
    if value.startswith("sqlite:///"):
        return value.removeprefix("sqlite:///")
    if value.startswith("sqlite://"):
        return value.removeprefix("sqlite://")
    return value


def _database_path_from_env() -> str:
    return os.getenv("DATABASE_PATH") or _sqlite_url_to_path(os.getenv("DATABASE_URL"))

class Database:
    def __init__(self, db_path: str = "bot_database.db"):
        self.db_path = db_path
        self.connection = None
    
    async def initialize(self):
        """Initialize database and create tables"""
        async with aiosqlite.connect(self.db_path) as db:
            # Giveaways table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS giveaways (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id INTEGER UNIQUE,
                    channel_id INTEGER,
                    host_id INTEGER,
                    prize TEXT,
                    duration_hours REAL,
                    created_at TIMESTAMP,
                    ends_at TIMESTAMP,
                    winner_count INTEGER DEFAULT 1,
                    allowed_roles TEXT DEFAULT '',
                    is_active BOOLEAN DEFAULT 1
                )
            ''')
            
            # Giveaway entries table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS giveaway_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    giveaway_id INTEGER,
                    user_id INTEGER,
                    FOREIGN KEY(giveaway_id) REFERENCES giveaways(id)
                )
            ''')
            
            # Partners table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS partners (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    server_name TEXT,
                    robux_reward INTEGER,
                    member_count INTEGER,
                    partner_message TEXT,
                    submitted_by INTEGER,
                    created_at TIMESTAMP,
                    approved_by INTEGER,
                    approved_at TIMESTAMP,
                    status TEXT DEFAULT 'pending',
                    robux_earned INTEGER DEFAULT 0
                )
            ''')
            
            # Partner logs table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS partner_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    partner_id INTEGER,
                    user_id INTEGER,
                    action TEXT,
                    approved BOOLEAN,
                    robux_amount INTEGER,
                    timestamp TIMESTAMP,
                    FOREIGN KEY(partner_id) REFERENCES partners(id)
                )
            ''')
            
            # Tickets table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket_id TEXT UNIQUE,
                    channel_id INTEGER,
                    user_id INTEGER,
                    ticket_type TEXT,
                    claimed_by INTEGER,
                    status TEXT DEFAULT 'open',
                    created_at TIMESTAMP,
                    closed_at TIMESTAMP,
                    close_reason TEXT
                )
            ''')
            
            # Marketing periods table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS marketing_periods (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    period_name TEXT,
                    start_date TIMESTAMP,
                    end_date TIMESTAMP,
                    remarks TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    total_partners INTEGER DEFAULT 0,
                    total_robux INTEGER DEFAULT 0
                )
            ''')
            
            # Marketer stats table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS marketer_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    period_id INTEGER,
                    user_id INTEGER,
                    partners_created INTEGER DEFAULT 0,
                    robux_earned INTEGER DEFAULT 0,
                    FOREIGN KEY(period_id) REFERENCES marketing_periods(id),
                    UNIQUE(period_id, user_id)
                )
            ''')
            
            # Server logs table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS server_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT,
                    user_id INTEGER,
                    action TEXT,
                    details TEXT,
                    timestamp TIMESTAMP
                )
            ''')
            
            # Commit initial table creation
            await db.commit()

            # Migrations for older DBs.
            try:
                async with db.execute("PRAGMA table_info(giveaways)") as cursor:
                    rows = await cursor.fetchall()
                    giveaway_cols = [r[1] for r in rows]
                if 'allowed_roles' not in giveaway_cols:
                    await db.execute("ALTER TABLE giveaways ADD COLUMN allowed_roles TEXT DEFAULT ''")
                    await db.commit()
                    logger.info("Migrated giveaways table: added allowed_roles column")

                async with db.execute("PRAGMA table_info(partners)") as cursor:
                    rows = await cursor.fetchall()
                    existing_cols = [r[1] for r in rows]
                if 'robux_reward' not in existing_cols:
                    await db.execute("ALTER TABLE partners ADD COLUMN robux_reward INTEGER DEFAULT 0")
                    await db.commit()
                    logger.info("Migrated partners table: added robux_reward column")

                # Ensure partner_message column exists (older DBs may lack it)
                if 'partner_message' not in existing_cols:
                    await db.execute("ALTER TABLE partners ADD COLUMN partner_message TEXT DEFAULT ''")
                    await db.commit()
                    logger.info("Migrated partners table: added partner_message column")
            except Exception:
                # If partners table doesn't exist yet or migration fails, skip (table was created above with column)
                pass
            logger.info("Database tables created successfully")

            # Products table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT,
                    price REAL DEFAULT 0,
                    stock INTEGER DEFAULT -1,
                    stripe_url TEXT,
                    robux_url TEXT,
                    delivery_content TEXT,
                    image_url TEXT,
                    thumbnail_url TEXT,
                    forum_channel_ids TEXT,
                    message_ids TEXT,
                    creator_id INTEGER,
                    tags TEXT,
                    category TEXT,
                    purchase_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP
                )
            ''')

            # Purchases table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS purchases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id INTEGER,
                    user_id INTEGER,
                    payment_method TEXT,
                    transaction_id TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP,
                    delivered_at TIMESTAMP,
                    FOREIGN KEY(product_id) REFERENCES products(id)
                )
            ''')

            # Robux verification queue
            await db.execute('''
                CREATE TABLE IF NOT EXISTS robux_verifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id INTEGER,
                    user_id INTEGER,
                    roblox_url TEXT,
                    reported_price INTEGER,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP,
                    resolved_by INTEGER,
                    resolved_at TIMESTAMP,
                    notes TEXT,
                    FOREIGN KEY(product_id) REFERENCES products(id)
                )
            ''')
            await db.commit()
            # Migration: add stock column if missing
            try:
                async with db.execute("PRAGMA table_info(products)") as cursor:
                    rows = await cursor.fetchall()
                    cols = [r[1] for r in rows]
                if 'stock' not in cols:
                    await db.execute("ALTER TABLE products ADD COLUMN stock INTEGER DEFAULT -1")
                    await db.commit()
                    logger.info('Migrated products table: added stock column')
            except Exception:
                pass
    
    async def add_giveaway(self, message_id: int, channel_id: int, host_id: int, 
                           prize: str, duration_hours: float, winner_count: int = 1):
        """Add a new giveaway"""
        async with aiosqlite.connect(self.db_path) as db:
            created_at = datetime.utcnow()
            ends_at = datetime.utcfromtimestamp(created_at.timestamp() + (duration_hours * 3600))
            cursor = await db.execute('''
                INSERT INTO giveaways 
                (message_id, channel_id, host_id, prize, duration_hours, created_at, ends_at, winner_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (message_id, channel_id, host_id, prize, duration_hours, created_at, ends_at, winner_count))
            
            await db.commit()
            try:
                return cursor.lastrowid
            except Exception:
                return None
    
    async def get_active_giveaways(self):
        """Get all active giveaways"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT * FROM giveaways WHERE is_active = 1') as cursor:
                return await cursor.fetchall()
    
    async def add_partner(
        self,
        server_name: str,
        robux_reward: int,
        member_count: int,
        partner_message: str,
        submitted_by: int,
        status: str = "approved",
    ) -> int:
        """Add a new partner"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                INSERT INTO partners (server_name, robux_reward, member_count, partner_message, submitted_by, created_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (server_name, robux_reward, member_count, partner_message, submitted_by, datetime.utcnow(), status))
            
            await db.commit()
            return cursor.lastrowid

    async def get_due_giveaways(self):
        """Get active giveaways whose end time has passed."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM giveaways WHERE is_active = 1 AND datetime(ends_at) <= datetime('now')"
            ) as cursor:
                return await cursor.fetchall()

    async def mark_giveaway_inactive(self, giveaway_id: int):
        """Mark a giveaway as inactive after processing."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE giveaways SET is_active = 0 WHERE id = ?", [giveaway_id])
            await db.commit()
    
    async def log_event(self, event_type: str, user_id: int, action: str, details: str = ""):
        """Log a server event"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO server_logs (event_type, user_id, action, details, timestamp)
                VALUES (?, ?, ?, ?, ?)
            ''', (event_type, user_id, action, details, datetime.utcnow()))
            
            await db.commit()
    
    async def execute(self, query: str, params: list = None):
        """Execute a query without returning results"""
        async with aiosqlite.connect(self.db_path) as db:
            if params:
                await db.execute(query, params)
            else:
                await db.execute(query)
            await db.commit()
    
    async def fetch_one(self, query: str, params: list = None):
        """Fetch a single row from the database"""
        async with aiosqlite.connect(self.db_path) as db:
            if params:
                async with db.execute(query, params) as cursor:
                    return await cursor.fetchone()
            else:
                async with db.execute(query) as cursor:
                    return await cursor.fetchone()
    
    async def fetch_all(self, query: str, params: list = None):
        """Fetch all rows from the database"""
        async with aiosqlite.connect(self.db_path) as db:
            if params:
                async with db.execute(query, params) as cursor:
                    return await cursor.fetchall()
            else:
                async with db.execute(query) as cursor:
                    return await cursor.fetchall()

    # Product helpers
    async def create_product(
        self,
        name: str,
        description: str = "",
        price: float = 0.0,
        stripe_url: str | None = None,
        robux_url: str | None = None,
        delivery_content: str | None = None,
        image_url: str | None = None,
        thumbnail_url: str | None = None,
        forum_channel_ids: str | None = None,
        message_ids: str | None = None,
        creator_id: int | None = None,
        tags: str | None = None,
        category: str | None = None,
        stock: int | None = None,
    ) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                INSERT INTO products
                (name, description, price, stripe_url, robux_url, delivery_content, image_url, thumbnail_url,
                 forum_channel_ids, message_ids, creator_id, tags, category, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                name, description, price, stripe_url, robux_url, delivery_content, image_url, thumbnail_url,
                forum_channel_ids or '', message_ids or '', creator_id, tags or '', category or '', datetime.utcnow()
            ))
            await db.commit()
            return cursor.lastrowid

    async def fetch_product_by_id(self, product_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT * FROM products WHERE id = ?', (product_id,)) as cursor:
                return await cursor.fetchone()

    async def fetch_all_products(self):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT * FROM products') as cursor:
                return await cursor.fetchall()

    async def update_product_message_ids(self, product_id: int, message_ids: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('UPDATE products SET message_ids = ? WHERE id = ?', (message_ids, product_id))
            await db.commit()

    async def update_product(self, product_id: int, **fields):
        if not fields:
            return
        cols = []
        params = []
        for k, v in fields.items():
            cols.append(f"{k} = ?")
            params.append(v)
        params.append(product_id)
        q = f"UPDATE products SET {', '.join(cols)} WHERE id = ?"
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(q, params)
            await db.commit()

    async def delete_product(self, product_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('DELETE FROM products WHERE id = ?', (product_id,))
            await db.execute('DELETE FROM purchases WHERE product_id = ?', (product_id,))
            await db.execute('DELETE FROM robux_verifications WHERE product_id = ?', (product_id,))
            await db.commit()

    async def fetch_pending_robux_verifications(self):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM robux_verifications WHERE status = 'pending'") as cursor:
                return await cursor.fetchall()

    async def resolve_robux_verification(self, verification_id: int, approved: bool, resolver_id: int, notes: str | None = None):
        async with aiosqlite.connect(self.db_path) as db:
            status = 'approved' if approved else 'rejected'
            await db.execute('UPDATE robux_verifications SET status = ?, resolved_by = ?, resolved_at = ?, notes = ? WHERE id = ?', (status, resolver_id, datetime.utcnow(), notes or '', verification_id))
            await db.commit()
            if approved:
                # create purchase record for the product/user
                async with db.execute('SELECT product_id, user_id FROM robux_verifications WHERE id = ?', (verification_id,)) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        await db.execute('INSERT INTO purchases (product_id, user_id, payment_method, status, created_at) VALUES (?, ?, ?, ?, ?)', (row[0], row[1], 'robux', 'completed', datetime.utcnow()))
                        await db.commit()

    async def add_purchase(self, product_id: int, user_id: int, payment_method: str, transaction_id: str | None = None, status: str = 'pending'):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO purchases (product_id, user_id, payment_method, transaction_id, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (product_id, user_id, payment_method, transaction_id, status, datetime.utcnow()))
            await db.commit()

    async def mark_purchase_completed(self, transaction_id: str, metadata: dict | None = None):
        async with aiosqlite.connect(self.db_path) as db:
            # Try to find by transaction_id
            await db.execute('UPDATE purchases SET status = ?, transaction_id = ? WHERE transaction_id = ? OR (transaction_id IS NULL AND ? IS NOT NULL AND ? = ?)',
                             ('completed', transaction_id, transaction_id, transaction_id, transaction_id, transaction_id))
            await db.commit()

    async def fetch_pending_deliveries(self):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT p.*, pr.delivery_content, pr.name FROM purchases p JOIN products pr ON p.product_id = pr.id WHERE p.status = 'completed' AND p.delivered_at IS NULL") as cursor:
                return await cursor.fetchall()

    async def mark_purchase_delivered(self, purchase_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('UPDATE purchases SET delivered_at = ?, status = ? WHERE id = ?', (datetime.utcnow(), 'delivered', purchase_id))
            await db.commit()

    async def mark_purchase_delivered_by_tx(self, transaction_id: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('UPDATE purchases SET delivered_at = ?, status = ? WHERE transaction_id = ?', (datetime.utcnow(), 'delivered', transaction_id))
            await db.commit()

    async def increment_product_purchase_count(self, product_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('UPDATE products SET purchase_count = purchase_count + 1 WHERE id = ?', (product_id,))
            await db.commit()

    async def add_robux_verification(self, product_id: int, user_id: int, roblox_url: str | None, reported_price: int | None = None):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                INSERT INTO robux_verifications (product_id, user_id, roblox_url, reported_price, created_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (product_id, user_id, roblox_url or '', reported_price or 0, datetime.utcnow()))
            await db.commit()
            return cursor.lastrowid

# Create global database instance
db = Database(_database_path_from_env())
