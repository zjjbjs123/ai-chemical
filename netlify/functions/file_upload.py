import os
import uuid
import logging
import json
from werkzeug.datastructures import FileStorage
from io import BytesIO

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def save_uploaded_file(file, upload_folder):
    if not os.path.exists(upload_folder):
        os.makedirs(upload_folder)
    unique_filename = str(uuid.uuid4()) + os.path.splitext(file.filename)[1]
    file_path = os.path.join(upload_folder, unique_filename)
    try:
        file.save(file_path)
        logging.debug(f"文件保存成功，路径: {file_path}")
        return file_path
    except Exception as e:
        logging.error(f"保存文件时出错: {e}")
        return None

def handler(event, context):
    try:
        # 获取请求方法
        http_method = event.get('httpMethod', 'GET')
        if http_method != 'POST':
            return {
                "statusCode": 405,
                "body": json.dumps({"message": "仅支持 POST 请求"})
            }

        # 获取请求头和请求体
        headers = event.get('headers', {})
        content_type = headers.get('Content-Type', '')

        # 检查是否是表单数据
        if 'multipart/form-data' not in content_type:
            return {
                "statusCode": 400,
                "body": json.dumps({"message": "请求体必须是 multipart/form-data 格式"})
            }

        # 从 event 中获取文件数据
        body = event.get('body', '')
        if isinstance(body, str):
            body = body.encode('utf-8')

        # 解析表单数据中的文件
        boundary = content_type.split('=')[1].encode('utf-8')
        parts = body.split(b'\r\n--' + boundary)[1:-1]
        file_parts = [part for part in parts if b'filename=' in part]

        if not file_parts:
            return {
                "statusCode": 400,
                "body": json.dumps({"message": "未找到上传的文件"})
            }

        # 假设只上传一个文件
        file_part = file_parts[0]
        filename_start = file_part.find(b'filename="') + len(b'filename="')
        filename_end = file_part.find(b'"', filename_start)
        filename = file_part[filename_start:filename_end].decode('utf-8')

        file_content_start = file_part.find(b'\r\n\r\n') + 4
        file_content = file_part[file_content_start:]

        # 创建 FileStorage 对象
        file = FileStorage(
            stream=BytesIO(file_content),
            filename=filename
        )

        # 获取上传文件夹
        upload_folder = 'uploads'  # 这里可以根据实际情况修改

        # 保存文件
        file_path = save_uploaded_file(file, upload_folder)

        if file_path:
            return {
                "statusCode": 200,
                "body": json.dumps({"message": "文件上传成功", "file_path": file_path})
            }
        else:
            return {
                "statusCode": 500,
                "body": json.dumps({"message": "文件上传失败"})
            }

    except Exception as e:
        logging.error(f"处理文件上传请求时出错: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"message": f"处理文件上传请求时出错: {str(e)}"})
        }