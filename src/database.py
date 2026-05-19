import sqlite3
import time
from config import GPS_VALIDITY_WINDOW, ABSOLUTE_SUBSCRIPTION_EXPIRY, UNACTIVATED_REAP_WINDOW

class EmergencyDB:
    DB_PATH = "emergency_node.db"

    @classmethod
    def _get_connection(cls):
        return sqlite3.connect(cls.DB_PATH)

    @classmethod
    def init(cls):
        with cls._get_connection() as conn:
            c = conn.cursor()
            # centralize storage performance parameters natively
            c.execute("PRAGMA journal_mode=WAL;")
            c.execute("PRAGMA synchronous=NORMAL;") 
            
            c.execute("CREATE TABLE IF NOT EXISTS subscriptions (node_id TEXT PRIMARY KEY, subscribed_at REAL NOT NULL)")
            c.execute("CREATE TABLE IF NOT EXISTS positions (node_id TEXT PRIMARY KEY, latitude REAL NOT NULL, longitude REAL NOT NULL, updated_at REAL NOT NULL)")
            c.execute("CREATE TABLE IF NOT EXISTS alert_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP, source TEXT, raw_payload TEXT, broadcast_message TEXT)")
            c.execute("CREATE TABLE IF NOT EXISTS dispatched_alerts (node_id TEXT, alert_hash TEXT, sent_at REAL, PRIMARY KEY (node_id, alert_hash))")
            conn.commit()

    @classmethod
    def add_subscription(cls, node_id):
        with cls._get_connection() as conn:
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO subscriptions (node_id, subscribed_at) VALUES (?, ?)", (node_id, time.time()))
            conn.commit()

    @classmethod
    def remove_subscription(cls, node_id):
        with cls._get_connection() as conn:
            c = conn.cursor()
            c.execute("DELETE FROM subscriptions WHERE node_id = ?", (node_id,))
            c.execute("DELETE FROM dispatched_alerts WHERE node_id = ?", (node_id,))
            conn.commit()

    @classmethod
    def is_subscribed(cls, node_id):
        with cls._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT 1 FROM subscriptions WHERE node_id = ?", (node_id,))
            return c.fetchone() is not None

    @classmethod
    def is_activated(cls, node_id):
        with cls._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT subscribed_at FROM subscriptions WHERE node_id = ?", (node_id,))
            sub_row = c.fetchone()
            if not sub_row: return False
            
            c.execute("SELECT updated_at FROM positions WHERE node_id = ?", (node_id,))
            pos_row = c.fetchone()
            if not pos_row: return False
            
            if pos_row[0] >= sub_row[0]: return True
            if (time.time() - pos_row[0]) <= GPS_VALIDITY_WINDOW: return True
            return False

    @classmethod
    def update_position(cls, node_id, lat, lon):
        with cls._get_connection() as conn:
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO positions (node_id, latitude, longitude, updated_at) VALUES (?, ?, ?, ?)", (node_id, lat, lon, time.time()))
            conn.commit()

    @classmethod
    def get_valid_position(cls, node_id):
        with cls._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT latitude, longitude, updated_at FROM positions WHERE node_id = ?", (node_id,))
            row = c.fetchone()
            if row and (time.time() - row[2]) <= GPS_VALIDITY_WINDOW:
                return row[0], row[1]
        return None
        
    @classmethod
    def get_raw_position(cls, node_id):
        with cls._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT latitude, longitude, updated_at FROM positions WHERE node_id = ?", (node_id,))
            return c.fetchone()

    @classmethod
    def get_all_activated_nodes(cls):
        activated = []
        with cls._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT node_id FROM subscriptions")
            subs = c.fetchall()
            for (node_id,) in subs:
                if cls.is_activated(node_id):
                    pos = cls.get_raw_position(node_id)
                    if pos:
                        activated.append((node_id, pos[0], pos[1]))
        return activated

    @classmethod
    def check_and_reap_subscriptions(cls):
        reaped_nodes = []
        now = time.time()
        with cls._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT node_id, subscribed_at FROM subscriptions")
            subs = c.fetchall()
            for node_id, subscribed_at in subs:
                if (now - subscribed_at) >= ABSOLUTE_SUBSCRIPTION_EXPIRY:
                    reaped_nodes.append(node_id)
                elif (now - subscribed_at) >= UNACTIVATED_REAP_WINDOW and not cls.is_activated(node_id):
                    reaped_nodes.append(node_id)
            for node_id in reaped_nodes:
                c.execute("DELETE FROM subscriptions WHERE node_id = ?", (node_id,))
                c.execute("DELETE FROM dispatched_alerts WHERE node_id = ?", (node_id,))
            conn.commit()
        return reaped_nodes

    @classmethod
    def mark_alert_dispatched(cls, node_id, alert_hash):
        with cls._get_connection() as conn:
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO dispatched_alerts (node_id, alert_hash, sent_at) VALUES (?, ?, ?)", (node_id, alert_hash, time.time()))
            conn.commit()

    @classmethod
    def has_alert_been_dispatched(cls, node_id, alert_hash):
        with cls._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT 1 FROM dispatched_alerts WHERE node_id = ? AND alert_hash = ?", (node_id, alert_hash))
            return c.fetchone() is not None