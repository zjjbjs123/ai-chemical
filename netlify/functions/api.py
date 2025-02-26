import json
from flask import Flask, request
from app.py import app  # 替换为你的 app.py 文件名

def handler(event, context):
    with app.test_request_context(
        path=event['path'],
        method=event['httpMethod'],
        headers=event.get('headers', {}),
        query_string=event.get('queryStringParameters', {}),
        body=event.get('body', None)
    ):
        try:
            response = app.full_dispatch_request()
        except Exception as e:
            return {
                'statusCode': 500,
                'body': json.dumps({'error': str(e)})
            }
        body = response.get_data(as_text=True)
        return {
            'statusCode': response.status_code,
            'headers': dict(response.headers),
            'body': body
        }