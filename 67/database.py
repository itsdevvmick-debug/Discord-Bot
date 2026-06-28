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

# Create global database instance
db = Database(_database_path_from_env())
