import sqlite3
import os
import random
import re
import bcrypt
import functools
from flask import Flask, render_template, request, redirect, url_for, jsonify, send_from_directory
from flask_cors import CORS
import logging
from database import get_db_connection, init_db
from file_upload import save_uploaded_file
import openai
import sys
import urllib.parse

app = Flask(__name__)
# 配置上传文件目录
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
# 确保 JSON 数据能正确处理中文
app.config['JSON_AS_ASCII'] = False
# 配置日志
logging.basicConfig(level=logging.DEBUG)
# 定义管理员用户名和密码（使用 bcrypt 哈希处理）
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = bcrypt.hashpw('password'.encode('utf-8'), bcrypt.gensalt())

CORS(app)  # 允许跨域请求

# 设置OpenAI（实际上是DeepSeek）的配置
openai.api_key = 'sk-4b233fdcd3964197af28cedcb28efaec'
MAX_RETRIES = 3
RETRY_DELAY = 2  # 每次重试的延迟时间（秒


@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@functools.lru_cache(maxsize=1)
def get_random_images():
    slide_folder = os.path.join('static', 'slide')
    allowed_extensions = ('.jpg', '.jpeg', '.png', '.gif')
    image_files = [f for f in os.listdir(slide_folder) if os.path.isfile(os.path.join(slide_folder, f)) and f.lower().endswith(allowed_extensions)]
    random.shuffle(image_files)
    return image_files

# 自定义 Jinja2 过滤器用于 URL 解码
@app.template_filter('url_decode')
def url_decode(s):
    return urllib.parse.unquote(s)

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password').encode('utf-8')
        if username == ADMIN_USERNAME and bcrypt.checkpw(password, ADMIN_PASSWORD):
            # 登录成功，重定向到管理页面
            return redirect(url_for('platformmanage'))
        else:
            # 登录失败，返回错误信息
            return "用户名或密码错误", 401
    return render_template('login.html')

@app.route('/platform')
def platform():
    with get_db_connection() as conn:
        try:
            menu_hierarchy = build_menu_hierarchy(conn)
            random_images = get_random_images()
            logging.info(f"传递给 platform.html 的 menu_hierarchy 数据: {menu_hierarchy}")
            return render_template('platform.html', menu_hierarchy=menu_hierarchy, random_images=random_images)
        except Exception as e:
            logging.error(f"获取平台菜单层级结构时出错: {e}")
            return "获取平台菜单信息出错", 500


@app.route('/platformmanage')
def platformmanage():
    with get_db_connection() as conn:
        try:
            menu_hierarchy = build_menu_hierarchy(conn)
            logging.info(f"传递给 platformmanage.html 的 menu_hierarchy 数据: {menu_hierarchy}")
            return render_template('platformmanage.html', menu_hierarchy=menu_hierarchy)
        except Exception as e:
            logging.error(f"获取平台菜单层级结构时出错: {e}")
            return "获取平台菜单信息出错", 500

@app.route('/create_menu', methods=['POST'])
def create_menu():
    try:
        parent_id = request.form.get('parent_id')
        menu_name = request.form.get('menu_name')
        menu_type = request.form.get('menu_type')

        logging.info(f"接收到的原始参数 - parent_id: {parent_id}, menu_name: {menu_name}, menu_type: {menu_type}")

        if parent_id == '' or parent_id.lower() == 'none':
            parent_id = None

        logging.info(f"处理后的参数 - parent_id: {parent_id}, menu_name: {menu_name}, menu_type: {menu_type}")

        with get_db_connection() as conn:
            if parent_id is None:
                result = conn.execute(
                    'SELECT MAX(sort_order) FROM menus WHERE COALESCE(parent_id, "") = ""').fetchone()
            else:
                result = conn.execute(
                    'SELECT MAX(sort_order) FROM menus WHERE parent_id =?', (parent_id,)).fetchone()

            max_sort_order = result[0] if result[0] is not None else 0
            new_sort_order = max_sort_order + 1

            content_type = None
            content = None

            cursor = conn.cursor()
            insert_query = 'INSERT INTO menus (parent_id, name, type, sort_order, content_type, content) VALUES (?,?,?,?,?,?)'
            insert_params = (parent_id, menu_name, menu_type, new_sort_order, content_type, content)

            logging.info(f"插入语句: {insert_query}")
            logging.info(f"插入参数: {insert_params}")

            cursor.execute(insert_query, insert_params)
            rows_affected = cursor.rowcount
            logging.info(f"插入操作受影响的行数: {rows_affected}")

            if rows_affected == 0:
                logging.error("插入操作未影响任何行，插入可能失败。")
                return jsonify({"status": "error", "message": "插入菜单记录失败，请检查数据库配置或数据格式。"}), 500

            new_menu_id = cursor.lastrowid
            logging.info(f"新创建菜单的 ID: {new_menu_id}")

            inserted_menu = conn.execute('SELECT * FROM menus WHERE id =?', (new_menu_id,)).fetchone()
            if not inserted_menu:
                logging.warning("插入记录查询失败，可能插入未成功。再次查询全量数据以排查：")
                all_menus = conn.execute('SELECT * FROM menus').fetchall()
                for menu in all_menus:
                    logging.info(f"数据库中现有菜单: {dict(menu)}")
                return jsonify({"status": "error", "message": "插入菜单记录后查询失败，请检查数据库状态。"}), 500

            return jsonify({"status": "success", "message": "菜单创建成功", "menu_id": new_menu_id}), 200

    except Exception as e:
        logging.error(f"创建菜单时出错: {e}")
        return jsonify({"status": "error", "message": f"创建菜单时出错: {e}"}), 500

# 在获取菜单层级结构时，需要递归地查询子菜单，以支持任意层级的菜单。
def build_menu_hierarchy(conn, parent_id=None, level=1):
    import logging
    logging.info(f"开始查询 parent_id 为 {parent_id}，层级为 {level} 的菜单")
    if parent_id is None:
        menus = conn.execute(
            'SELECT * FROM menus WHERE parent_id IS NULL ORDER BY sort_order').fetchall()
    else:
        menus = conn.execute(
            'SELECT * FROM menus WHERE parent_id =? ORDER BY sort_order', (parent_id,)).fetchall()
    logging.info(f"查询到 {len(menus)} 条 parent_id 为 {parent_id}，层级为 {level} 的菜单记录")
    menu_list = []
    for menu in menus:
        menu_dict = {key: menu[key] for key in menu.keys()}
        menu_dict['level'] = level
        logging.info(f"处理菜单 ID 为 {menu_dict['id']}，层级为 {level} 的菜单")
        if level < 100:  # 可以根据实际情况调整深度限制
            sub_menus = build_menu_hierarchy(conn, menu_dict.get('id'), level + 1)
            menu_dict['sub_menus'] = sub_menus
            menu_dict['has_sub_menus'] = len(sub_menus) > 0  # 添加 has_sub_menus 标志位
        else:
            menu_dict['sub_menus'] = []
            menu_dict['has_sub_menus'] = False
        menu_list.append(menu_dict)
    return menu_list



@app.route('/get_parent_id')
def get_parent_id():
    menu_id = request.args.get('menu_id')
    try:
        with get_db_connection() as conn:
            result = conn.execute('SELECT parent_id FROM menus WHERE id =?', (menu_id,)).fetchone()
            if result:
                parent_id = result['parent_id']
                return jsonify({"status": "success", "parent_id": parent_id})
            else:
                return jsonify({"status": "error", "message": "未找到对应的菜单记录"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/delete_menu', methods=['POST'])
def delete_menu():
    menu_id = request.form.get('menu_id')
    with get_db_connection() as conn:
        try:
            conn.execute('DELETE FROM menus WHERE id =?', (menu_id,))
            conn.commit()  # 提交事务
        except Exception as e:
            logging.error(f"删除菜单时出错: {e}")
            return f"删除菜单时出错: {e}", 500
    return redirect(url_for('platformmanage'))


@app.route('/edit_menu_name', methods=['POST'])
def edit_menu_name():
    menu_id = request.form.get('menu_id')
    new_name = request.form.get('new_name')
    with get_db_connection() as conn:
        try:
            conn.execute('UPDATE menus SET name =? WHERE id =?', (new_name, menu_id))
        except Exception as e:
            logging.error(f"编辑菜单名称时出错: {e}")
            return f"编辑菜单名称时出错: {e}", 500
    return redirect(url_for('platformmanage'))


def swap_sort_order(conn, menu1_id, menu2_id):
    menu1 = conn.execute('SELECT sort_order FROM menus WHERE id =?', (menu1_id,)).fetchone()
    menu2 = conn.execute('SELECT sort_order FROM menus WHERE id =?', (menu2_id,)).fetchone()
    if menu1 and menu2:
        conn.execute('UPDATE menus SET sort_order =? WHERE id =?', (menu2['sort_order'], menu1_id))
        conn.execute('UPDATE menus SET sort_order =? WHERE id =?', (menu1['sort_order'], menu2_id))

@app.route('/sort_menu', methods=['GET', 'POST'])
def sort_menu():
    menu_id = request.values.get('menu_id')
    direction = request.values.get('direction')
    isFirstLevel_str = request.values.get('isFirstLevel')
    isFirstLevel = isFirstLevel_str.lower() == 'true' if isFirstLevel_str else False

    logging.info(f"排序请求：menu_id={menu_id}, direction={direction}, isFirstLevel={isFirstLevel}")

    with get_db_connection() as conn:
        try:
            current_menu = conn.execute('SELECT * FROM menus WHERE id =?', (menu_id,)).fetchone()
            if not current_menu:
                logging.error(f"未找到 ID 为 {menu_id} 的菜单记录")
                return render_template('error.html', message=f"未找到 ID 为 {menu_id} 的菜单记录"), 404
            current_sort_order = current_menu['sort_order']
            parent_id = current_menu['parent_id']

            logging.info(f"当前菜单排序顺序：{current_sort_order}, 父菜单 ID：{parent_id}")

            if isFirstLevel:
                if direction == 'up':
                    prev_menu = conn.execute(
                        'SELECT * FROM menus WHERE COALESCE(parent_id, "") = "" AND sort_order < ? ORDER BY sort_order DESC LIMIT 1',
                        (current_sort_order,)).fetchone()
                    if prev_menu:
                        logging.info(f"找到上一个菜单，ID：{prev_menu['id']}")
                        swap_sort_order(conn, menu_id, prev_menu['id'])
                    else:
                        logging.info("未找到上一个菜单，无法上移")
                        return render_template('error.html', message="未找到上一个菜单，无法上移"), 400
                elif direction == 'down':
                    next_menu = conn.execute(
                        'SELECT * FROM menus WHERE COALESCE(parent_id, "") = "" AND sort_order > ? ORDER BY sort_order ASC LIMIT 1',
                        (current_sort_order,)).fetchone()
                    if next_menu:
                        logging.info(f"找到下一个菜单，ID：{next_menu['id']}")
                        swap_sort_order(conn, menu_id, next_menu['id'])
                    else:
                        logging.info("未找到下一个菜单，无法下移")
                        return render_template('error.html', message="未找到下一个菜单，无法下移"), 400
            else:
                if direction == 'up':
                    prev_menu = conn.execute(
                        'SELECT * FROM menus WHERE parent_id =? AND sort_order < ? ORDER BY sort_order DESC LIMIT 1',
                        (parent_id, current_sort_order)).fetchone()
                    if prev_menu:
                        logging.info(f"找到上一个子菜单，ID：{prev_menu['id']}")
                        swap_sort_order(conn, menu_id, prev_menu['id'])
                    else:
                        logging.info("未找到上一个子菜单，无法上移")
                        return render_template('error.html', message="未找到上一个子菜单，无法上移"), 400
                elif direction == 'down':
                    next_menu = conn.execute(
                        'SELECT * FROM menus WHERE parent_id =? AND sort_order > ? ORDER BY sort_order ASC LIMIT 1',
                        (parent_id, current_sort_order)).fetchone()
                    if next_menu:
                        logging.info(f"找到下一个子菜单，ID：{next_menu['id']}")
                        swap_sort_order(conn, menu_id, next_menu['id'])
                    else:
                        logging.info("未找到下一个子菜单，无法下移")
                        return render_template('error.html', message="未找到下一个子菜单，无法下移"), 400

        except Exception as e:
            logging.error(f"排序菜单时出错: {e}")
            return render_template('error.html', message=f"排序菜单时出错: {e}"), 500

    return redirect(url_for('platformmanage'))

# 定义 save_uploaded_file 函数
def save_uploaded_file(file, upload_folder):
    if not os.path.exists(upload_folder):
        os.makedirs(upload_folder)
    filename = file.filename
    file_path = os.path.join(upload_folder, filename)
    try:
        file.save(file_path)
        return file_path
    except Exception as e:
        logging.error(f"保存文件时出错: {e}")
        return None

def return_error(status, message):
    """封装返回错误信息的函数"""
    logging.error(message)
    return jsonify({"status": "error", "message": message}), status
    

@app.route('/edit_sub_menu_content', methods=['POST'])
def edit_sub_menu_content():
    logging.debug(f"请求方法: {request.method}")
    logging.debug(f"请求表单数据: {request.form}")
    logging.debug(f"请求文件数据: {request.files}")

    menu_id = request.form.get('menu_id')
    content_type = request.form.get('content_type')
    content = None
    description = request.form.get('description')

    def return_error(status, message):
        """封装返回错误信息的函数"""
        logging.error(message)
        return jsonify({"status": "error", "message": message}), status

    if content_type == 'web_link':
        content_values = request.form.getlist('content')
        url_regex = re.compile(r'^(https?|ftp):\/\/[^\s/$.?#]+[^\s]*$')
        logging.debug(f"输入的链接列表: {content_values}")
        valid_url = next((value for value in content_values if url_regex.match(value)), None)
        if not valid_url:
            return return_error(400, "请输入有效的网页链接")
        content = valid_url
        logging.debug(f"有效的链接: {content}")
    elif content_type == 'attachment':
        file = request.files.get('content')
        if file:
            upload_folder = app.config.get('UPLOAD_FOLDER')
            if not upload_folder:
                return return_error(500, "UPLOAD_FOLDER 配置缺失")
            file_path = save_uploaded_file(file, upload_folder)
            if file_path:
                content = file_path
            else:
                return return_error(500, "保存附件文件时出错")
        else:
            return return_error(400, "请选择要上传的附件")
    elif content_type == 'text':
        content = request.form.get('content')
        logging.debug(f"接收到的文本内容: {content}")
        if not content:
            return return_error(400, "请输入文本内容")
    elif content_type == 'executable':
        file_list = request.files.getlist('content')
        file = next((f for f in file_list if f.filename), None)
        logging.debug(f"接收到的文件列表: {file_list}")
        if file:
            upload_folder = app.config.get('UPLOAD_FOLDER')
            if not upload_folder:
                return return_error(500, "UPLOAD_FOLDER 配置缺失")
            file_path = save_uploaded_file(file, upload_folder)
            if file_path:
                content = file_path
            else:
                return return_error(500, "保存可执行程序文件时出错")
        else:
            return return_error(400, "请选择要上传的可执行程序文件")

    logging.debug(f"接收到的 menu_id: {menu_id}, content_type: {content_type}, content: {content}, description: {description}")
    with get_db_connection() as conn:
        try:
            sql = 'UPDATE menus SET content_type =?, content =?, description =? WHERE id =?'
            logging.debug(f"执行的 SQL 语句: {sql}, 参数: ({content_type}, {content}, {description}, {menu_id})")
            cursor = conn.cursor()
            cursor.execute(sql, (content_type, content, description, menu_id))
            if cursor.rowcount == 0:
                return return_error(404, f"未找到 menu_id 为 {menu_id} 的记录，更新失败。")
        except sqlite3.OperationalError as e:
            return return_error(500, f"执行数据库操作时出现操作错误: {e}")
        except sqlite3.IntegrityError as e:
            return return_error(500, f"执行数据库操作时出现数据完整性错误: {e}")
        except Exception as e:
            return return_error(500, f"编辑子菜单内容时数据库操作出错: {e}")

    logging.info("子菜单内容编辑成功")
    return redirect(url_for('platformmanage'))



@app.route('/get_menu_content', methods=['GET'])
def get_menu_content():
    menu_id = request.args.get('menu_id')
    logging.debug(f'接收到的 menu_id: {menu_id}')
    with get_db_connection() as conn:
        try:
            cursor = conn.cursor()
            cursor.execute('SELECT content_type, content FROM menus WHERE id =?', (menu_id,))
            result = cursor.fetchone()
            logging.debug(f'Result from database: {result}')
            if result:
                content_type = result['content_type']
                content = result['content']
                logging.debug(f'Content type: {content_type}')
                logging.debug(f'Content: {content}')

                return jsonify({
                    'content_type': content_type,
                    'content': content
                })
            return jsonify({}), 404
        except Exception as e:
            logging.error(f"查询菜单内容时出错: {e}")
            return jsonify({}), 500


@app.route('/run_executable', methods=['POST'])
def run_executable():
    menu_id = request.form.get('menu_id')
    with get_db_connection() as conn:
        try:
            cursor = conn.cursor()
            cursor.execute('SELECT content FROM menus WHERE id =? AND content_type = "executable"', (menu_id,))
            result = cursor.fetchone()
            if result:
                executable_path = result['content']
                custom_protocol = f"myapp://{executable_path.replace('\\', '/')}"
                try:
                    # 这里可根据实际情况调整逻辑，目前只是返回协议链接
                    return custom_protocol
                except Exception as e:
                    return f"启动程序时出错：{str(e)}", 500
            else:
                return "未找到对应的可执行程序记录", 404
        except Exception as e:
            logging.error(f"查询可执行程序路径时出错: {e}")
            return f"查询可执行程序路径时出错: {e}", 500

@app.route('/download_attachment/<path:filename>')
def download_attachment(filename):
    # 只提取文件名
    real_filename = os.path.basename(filename)
    upload_folder = app.config['UPLOAD_FOLDER']
    file_path = os.path.join(upload_folder, real_filename)
    logging.info(f"尝试下载文件: {file_path}")
    if os.path.exists(file_path):
        logging.info("文件存在，开始下载")
        return send_from_directory(upload_folder, real_filename, as_attachment=True)
    else:
        logging.error("文件不存在")
        abort(404, description="文件不存在")
    
@app.route('/create_menu_page', methods=['GET'])
def create_menu_page():
    with get_db_connection() as conn:
        try:
            first_level_menus = conn.execute('SELECT * FROM menus WHERE COALESCE(parent_id, "") = "" ORDER BY sort_order').fetchall()
            return render_template('create_menu.html', first_level_menus=first_level_menus)
        except Exception as e:
            logging.error(f"获取一级菜单时出错: {e}")
            return "获取一级菜单信息出错", 500

@app.route('/edit_sub_menu_content_page/<menu_id>', methods=['GET'])
def edit_sub_menu_content_page(menu_id):
    with get_db_connection() as conn:
        try:
            menu = conn.execute('SELECT * FROM menus WHERE id =?', (menu_id,)).fetchone()
            if menu:
                menu_dict = dict(menu)
                if menu_dict.get('content_type') in ['executable', 'attachment']:
                    menu_dict['filename'] = os.path.basename(menu_dict.get('content', ''))
                logging.info(f"传递给模板的菜单数据: {menu_dict}")
                return render_template('edit_sub_menu_content.html', menu=menu_dict)
            return "未找到对应的菜单记录", 404
        except Exception as e:
            logging.error(f"获取菜单信息时出错: {e}")
            return "获取菜单信息出错", 500

@app.route('/edit_menu_name_page/<int:menu_id>', methods=['GET'])
def edit_menu_name_page(menu_id):
    try:
        # 使用 with 语句管理数据库连接上下文
        with get_db_connection() as conn:
            # 从数据库中查询指定菜单 ID 的菜单信息
            menu = conn.execute('SELECT * FROM menus WHERE id =?', (menu_id,)).fetchone()

        if menu:
            # 如果查询到菜单信息，将其转换为字典
            menu_dict = dict(menu)
            # 渲染编辑菜单名称的 HTML 模板，并传递菜单信息
            return render_template('edit_menu_name.html', menu=menu_dict)
        else:
            # 如果未查询到菜单信息，返回错误提示
            return "未找到对应的菜单记录", 404
    except Exception as e:
        # 若出现异常，记录错误日志并返回错误提示
        logging.error(f"获取菜单信息时出错: {e}")
        return "获取菜单信息出错", 500

#处理菜单字段（名称和类型）的更新
@app.route('/update_menu_field', methods=['GET'])
def update_menu_field():
    menu_id = request.args.get('menu_id')
    field = request.args.get('field')
    new_value = request.args.get('new_value')
    try:
        with get_db_connection() as conn:
            if field == 'name':
                conn.execute('UPDATE menus SET name =? WHERE id =?', (new_value, menu_id))
            elif field == 'type':
                conn.execute('UPDATE menus SET type =? WHERE id =?', (new_value, menu_id))
            conn.commit()
            return jsonify({"success": True})
    except Exception as e:
        logging.error(f"更新菜单字段时出错: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


def generate_reg_file():
    executable_path = os.path.abspath(__file__)
    reg_content = rf"""
Windows Registry Editor Version 5.00

[HKEY_CLASSES_ROOT\myapp]
@="URL:MyApp Protocol"
"URL Protocol"=""

[HKEY_CLASSES_ROOT\myapp\shell]

[HKEY_CLASSES_ROOT\myapp\shell\open]

[HKEY_CLASSES_ROOT\myapp\shell\open\command]
@="{executable_path}" "%1"
    """
    reg_file_path = "myapp_registration.reg"
    with open(reg_file_path, 'w') as f:
        f.write(reg_content)
    return reg_file_path

@app.route('/deepseek_proxy', methods=['POST'])
def deepseek_proxy():
    data = request.get_json()
    prompt = data.get('prompt')
    try:
        client = openai.OpenAI(
            api_key=openai.api_key,
            base_url='https://api.deepseek.com'
        )
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "You are a helpful assistant"},
                {"role": "user", "content": prompt}
            ],
            stream=False
        )
        content = response.choices[0].message.content
        return jsonify({'content': content})
    except OpenAIError as e:
        return jsonify({'error': f'OpenAI API error: {str(e)}'}), 500
    except ValueError as e:
        print(f"JSON 解析错误: {e}")
        return jsonify({'error': 'Invalid JSON response from API'}), 500
    except Exception as e:
        import traceback
        print(f"An error occurred: {str(e)}")
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500



if __name__ == '__main__':
    init_db()
    if len(sys.argv) > 1 and sys.argv[1] == '--generate-reg':
        reg_file = generate_reg_file()
        print(f"已生成注册表文件: {reg_file}")
        import subprocess
        try:
            subprocess.run(['regedit', '/s', reg_file])
            print("注册表文件已自动运行")
        except Exception as e:
            print(f"运行注册表文件时出错: {e}")
    else:
        app.run(debug=True)