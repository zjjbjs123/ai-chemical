import os
import uuid
import logging

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