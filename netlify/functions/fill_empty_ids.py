import sqlite3
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def handler(event, context):
    try:
        # 连接到数据库
        conn = sqlite3.connect('menus.db')
        cursor = conn.cursor()

        # 找出最大的 id
        cursor.execute('SELECT MAX(id) FROM menus')
        max_id_result = cursor.fetchone()[0]
        if max_id_result is None:
            next_id = 1
        else:
            next_id = max_id_result + 1

        # 查询 id 为空的记录
        cursor.execute('SELECT rowid FROM menus WHERE id IS NULL OR id = ""')
        empty_id_rows = cursor.fetchall()

        # 为每条 id 为空的记录生成并更新唯一的 id
        for row in empty_id_rows:
            rowid = row[0]
            cursor.execute('UPDATE menus SET id =? WHERE rowid =?', (next_id, rowid))
            next_id += 1

        # 提交更改
        conn.commit()
        logging.info("ID 补齐操作完成。")

        # 关闭连接
        conn.close()

        return {
            "statusCode": 200,
            "body": "ID 补齐操作完成。"
        }
    except Exception as e:
        logging.error(f"执行 ID 补齐操作时出错: {e}")
        return {
            "statusCode": 500,
            "body": f"执行 ID 补齐操作时出错: {str(e)}"
        }

if __name__ == "__main__":
    # 模拟 event 和 context 参数
    event = {}
    context = {}
    result = handler(event, context)
    print(result)