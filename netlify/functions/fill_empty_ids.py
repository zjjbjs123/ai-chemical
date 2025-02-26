import sqlite3

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

# 提交更改并关闭连接
conn.commit()
conn.close()

print("ID 补齐操作完成。")