from __future__ import print_function
from elasticsearch import Elasticsearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth
from botocore.exceptions import ClientError
from elasticsearch import Elasticsearch
import datetime as datetime
import botocore
import logging
import boto3
import base64
import gzip
import time
import json
import io
import csv
import os
import gzip


################################################################################################################
#   References
################################################################################################################
# https://stackoverflow.com/questions/37703634/how-to-import-a-text-file-on-aws-s3-into-pandas-without-writing-to-disk
# https://docs.aws.amazon.com/AmazonS3/latest/dev/notification-content-structure.html
# https://elasticsearch-py.readthedocs.io/en/7.10.0/


################################################################################################################
#   Config
################################################################################################################
region = os.environ['AWS_REGION']
QUEUEURL = os.environ['QUEUEURL']
ELASTICSEARCH_HOST = os.environ['ELASTICSEARCH_HOST']
debug = os.getenv('DEBUG', False) in (True, 'True')

file_path = '/tmp/record.json.gz'
sqs_client = boto3.client('sqs')
s3_client = boto3.resource('s3')

# Connect to Elasticsearch Service Domain
service = 'es'
credentials = boto3.Session().get_credentials()
awsauth = AWS4Auth(credentials.access_key, credentials.secret_key, region, service, session_token=credentials.token)
elasticsearchclient = Elasticsearch(
    hosts = [{'host': ELASTICSEARCH_HOST, 'port': 443}],
    http_auth = awsauth,
    use_ssl = True,
    verify_certs = True,
    connection_class = RequestsHttpConnection
)


def get_elasticsearch_time(time_from_record):
    # Need:
    # 2018-04-23T10:45:13.899Z
    # Have:
    # [23/Nov/2020:07:43:07
    # Got:
    # 2020-Nov-23T07:43:07Z
    if debug:
        print('time_from_record=' + time_from_record)
    year = time_from_record[8:12]
    month = time_from_record[4:7]
    day = time_from_record[1:3]
    hour = time_from_record[13:15]
    minutes = time_from_record[16:18]
    seconds = time_from_record[19:21]

    # convert month name to month number
    month_name = month
    datetime_object = datetime.datetime.strptime(month_name, "%b")
    month_number = datetime_object.month
    month_number_string = str(month_number)

    if debug:
        print(year)
        print(month_number_string)
        print(day)
        print(hour)
        print(minutes)
        print(seconds)

    newtime = str( year + '-' + month_number_string + '-' + day + 'T' + hour + ':' + minutes + ':' + seconds + 'Z' )

    return newtime


def get_sqs_message(QUEUEURL, sqs_client):
    ###### Example of string data that was sent:#########
    # payload = { 
    # "bucketname": bucketname, 
    # "s3_file_name": s3_file_name
    # }
    ################################################

    receive_message_response = dict()
    while 'Messages' not in receive_message_response:
        receive_message_response = sqs_client.receive_message(
            QueueUrl=QUEUEURL,
            # AttributeNames=[
            #     'All'|'Policy'|'VisibilityTimeout'|'MaximumMessageSize'|'MessageRetentionPeriod'|'ApproximateNumberOfMessages'|'ApproximateNumberOfMessagesNotVisible'|'CreatedTimestamp'|'LastModifiedTimestamp'|'QueueArn'|'ApproximateNumberOfMessagesDelayed'|'DelaySeconds'|'ReceiveMessageWaitTimeSeconds'|'RedrivePolicy'|'FifoQueue'|'ContentBasedDeduplication'|'KmsMasterKeyId'|'KmsDataKeyReusePeriodSeconds',
            # ],
            # MessageAttributeNames=[
            #     'string',
            # ],
            MaxNumberOfMessages=1
            # VisibilityTimeout=123,
            # WaitTimeSeconds=123,
            # ReceiveRequestAttemptId='string'
        )
        if 'Messages' in receive_message_response:
            number_of_messages = len(receive_message_response['Messages'])
            if debug:
                print("\n received {0} messages!! ....Processing message \n".format(number_of_messages))
            break
        else:
            print("\n received 0 messages!! waiting.....5 seconds before retrying \n")
            time.sleep(5)
            continue
        

    ReceiptHandle = receive_message_response['Messages'][0]['ReceiptHandle']
    delete_message_response = sqs_client.delete_message(
    QueueUrl=QUEUEURL,
    ReceiptHandle=ReceiptHandle
    )
    if debug:
        print("delete_message_response = {0}".format(delete_message_response))
    return receive_message_response


def retrieve_s3_file(message):
    ################################################################################################################
    #   Unpack the message from SQS and get bucket name and object name
    ################################################################################################################
    if debug:
        print("\nmessage = {0}".format(message))
        print("\ntype(message) = {0}\n".format(type(message)))

    message_body = message['Body']
    if debug:
        print("\nmessage_body = {0}".format(message_body))
        print("\ntype(message_body) = {0}\n".format(type(message_body)))

    message_body_dict = json.loads(message_body)
    if debug:
        print("\nmessage_body_dict = {0}".format(message_body_dict))
        print("\ntype(message_body_dict) = {0}\n".format(type(message_body_dict)))

    message_within_message_body_str = message_body_dict['Message']
    if debug:
        print("\nmessage_within_message_body_str = {0}".format(message_within_message_body_str))
        print("\ntype(message_within_message_body_str) = {0}\n".format(type(message_within_message_body_str)))

    message_within_message_body = json.loads(message_within_message_body_str)
    if debug:
        print("\nmessage_within_message_body = {0}".format(message_within_message_body))
        print("\ntype(message_within_message_body) = {0}\n".format(type(message_within_message_body)))

    try:
        s3_notification_records = message_within_message_body['Records']
    except:
        print("Failed to retrieve \'Records\' from message_within_message_body! ")
        if message_within_message_body['Event'] == "s3:TestEvent":
            print("Found Amazon S3 notification TestEvent")               
            print("TestEvent=\n{0}".format(message_within_message_body["Event"]) )                     #https://docs.aws.amazon.com/AmazonS3/latest/dev/notification-content-structure.html
            raise Exception("....Skipping message")

    if debug:
        print("\ns3_notification_records = {0}".format(s3_notification_records))

    s3_bucket_name = s3_notification_records[0]['s3']['bucket']['name']
    s3_object_key = s3_notification_records[0]['s3']['object']['key']
    if debug:
        print(s3_bucket_name + ":" + s3_object_key)

    ################################################################################################################
    #   Get the data from S3  
    ################################################################################################################
    try:
        s3_client.Bucket(s3_bucket_name).download_file(s3_object_key, file_path)
        if debug:
            print("\n S3 File Download: COMPLETE\n")
    except botocore.exceptions.ClientError as e:
        if e.response['Error']['Code'] == "404":
            print("The object does not exist.")
        else:
            raise


def get_json_data_from_local_file():
    ################################################################################################################
    #   Get the data from S3 in JSON format
    ################################################################################################################
    # with open(file_path, 'r') as f:
    #     json_data = json.load(f)

    f = gzip.open(file_path,'rb')
    file_content_bytes = f.read()
    file_content = file_content_bytes.decode("utf-8")
    json_data = json.loads(file_content)

    if debug:
        print("\n\nDISPLAY JSON FILE CONTENTS")
        print(json_data)

    return json_data


def send_object_to_elasticsearch(json_data_from_local_file):
    ################################################################################################################
    #   for each object, Put records into the Elasticsearch cluster
    ################################################################################################################    
    for json_data in json_data_from_local_file['Records']:

        # for key in json_data:
        #     if debug:
        #         print("\n(Starting) key = {0}".format(key))
        #         print("\n(Starting) value = {0}".format(json_data[key]))
        #         print("\n(Starting) type(value) = {0}\n".format( type(json_data[key]) ))


        # Fix Time for Elasticsearch
        # Time = json_data['Time']
        # TimeOffset = json_data['Time - Offset']
        # json_data['TimeForElasticSearch'] = get_elasticsearch_time(Time)

        ################################################################################################################
        #   for each object, set the correct data type in the dictionary
        ################################################################################################################
        for key in json_data:
            if debug:
                print("\n(Starting) key = {0}".format(key))
                print("\n(Starting) value = {0}".format(json_data[key]))
                print("\n(Starting) type(value) = {0}\n".format( type(json_data[key]) ))
            json_data[key] = str(json_data[key])
            if debug:
                print("\n(Final) key = {0}".format(key))
                print("\n(Final) value = {0}".format(json_data[key]))
                print("\n(Final) type(value) = {0}\n".format( type(json_data[key]) ))

        index_prefix = "cloudtrail"
        service = json_data['eventSource']
        eventName = json_data['eventName']
        index_name_caps = index_prefix + "-" + service + "-" + eventName
        index_name = index_name_caps.lower()


        # Put the record into the Elasticsearch Service Domain
        try:
            res = elasticsearchclient.index(index=index_name, body=json_data)
            print('res[\'result\']=')
            print(res['result'])
            print('\nSUCCESS: SENDING into the Elasticsearch Service Domain one at a time')
        except Exception as e:
            print('\nFAILED: SENDING into the Elasticsearch Service Domain one at a time\n')
            print(e)
            exit(1)

    print('COMPLETED: Putting {0} records into the Elasticsearch Service Domain one at a time'.format( len(json_data_from_local_file) ))

################################################################################################################
################################################################################################################
#   LAMBDA HANDLER 
################################################################################################################
################################################################################################################
def lambda_handler(event, context):
    if debug:
        print("\n Lambda event={0}\n".format(json.dumps(event)))

    if context == "-": #RUNNING A LOCAL EXECUTION 
        # Todo 
        # secret_dictionary = get_secret(context)
        for Message in event['Messages']:
            try:
                retrieve_s3_file(Message)
                json_data_from_local_file = get_json_data_from_local_file()
                send_object_to_elasticsearch(json_data_from_local_file)
            except:
                print("Failed to process Message: {0}".format(Message) )
    else:   #RUNNING A LAMBDA INVOCATION
        for Record in event['Records']:
            try:
                retrieve_s3_file(Record)
                json_data_from_local_file = get_json_data_from_local_file()
                send_object_to_elasticsearch(json_data_from_local_file)
            except:
                print("Failed to process Record: {0}".format(Record) )
################################################################################################################
################################################################################################################
#   LAMBDA HANDLER 
################################################################################################################
################################################################################################################



################################################################################################################
# LOCAL TESTING and DEBUGGING  
################################################################################################################
if __name__ == "__main__":
    context = "-"
    # for x in range(0, 300):
    while True:
        event = get_sqs_message(QUEUEURL, sqs_client)
        if debug:
            print("\n event={0}\n".format(json.dumps(event)))
        lambda_handler(event,context)

