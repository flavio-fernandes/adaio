import json
import logging
import os

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

getMethod = 'GET'
postMethod = 'POST'

dataPath = '/data'
DB_FILE = "/tmp/db.json"


def lambda_handler(event, context):
    logger.info(event)
    httpMethod = event['httpMethod']
    path = event['path']
    if path == dataPath:
        if httpMethod == getMethod:
            response = buildResponse(200, _read())
        elif httpMethod == postMethod:
            response = postData(json.loads(event['body']))
        else:
            response = buildResponse(501, f'Unexpected method: {httpMethod}')
    else:
        response = buildResponse(404)
    return response


def buildResponse(statusCode, body=None):
    response = {'statusCode': statusCode, 'headers': {'Content-Type': 'application/json',
                                                      'Access-Control-Allow-Origin': '*', }, }
    if body is not None:
        response['body'] = json.dumps(body)
    logger.debug(response)
    return response


def postData(newData):
    VALID_KEYS = ("text", "bays", "last-update",)
    data = _read()
    for key in VALID_KEYS:
        newValue = newData.get(key, data.get(key))
        if newValue and len(newValue) > 80:
            logger.exception(f'Refusing to store value for data key: {key} len: {len(newValue)}')
            continue
        data[key] = newValue
    _save(data)
    return buildResponse(200, data)


def _read():
    try:
        with open(DB_FILE, "r") as infile:
            return json.load(infile)
    except FileNotFoundError:
        pass
    return {}


def _save(data):
    logger.debug("Saving data: %s", data)
    tmp_filename = DB_FILE + ".tmp"
    with open(tmp_filename, "w") as outfile:
        json.dump(data, outfile)
    os.rename(tmp_filename, DB_FILE)

