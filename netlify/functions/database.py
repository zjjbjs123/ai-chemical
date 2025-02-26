from contextlib import contextmanager
import sqlite3
import logging
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

@contextmanager
def get_db_connection():
    try:
        conn = sqlite3.connect('menus.db')
        conn.row_factory = sqlite3.Row  # 确保 row_factory 设置为 sqlite3.Row
        logging.info("数据库连接成功")
        yield conn
        conn.commit()
        logging.info("事务提交成功")
    except Exception as e:
        logging.error(f"数据库操作出错: {e}")
        conn.rollback()
    finally:
        if conn:
            conn.close()
            logging.info("数据库连接关闭")

def init_db():
    with get_db_connection() as conn:
        try:
            # 创建 menus 表
            conn.execute('''
                CREATE TABLE IF NOT EXISTS menus (
                    id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
                    parent_id INTEGER,
                    name TEXT,
                    type TEXT,
                    sort_order INTEGER,
                    content_type TEXT,
                    content TEXT
                )
            ''')
            logging.info("数据库表初始化成功")
        except Exception as e:
            logging.error(f"数据库表初始化出错: {e}")