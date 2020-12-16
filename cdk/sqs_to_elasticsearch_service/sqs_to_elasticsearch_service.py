from __future__ import print_function
from botocore.exceptions import ClientError
import datetime as datetime
import pandas as pd
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


################################################################################################################
#   References
################################################################################################################
# https://stackoverflow.com/questions/37703634/how-to-import-a-text-file-on-aws-s3-into-pandas-without-writing-to-disk
# https://docs.aws.amazon.com/AmazonS3/latest/dev/notification-content-structure.html


################################################################################################################
#   Config
################################################################################################################
region = os.environ['AWS_REGION']
firehose_name = os.environ['FIREHOSE_NAME']
QUEUEURL = os.environ['QUEUEURL']
file_path = '/tmp/record.json'
sqs_client = boto3.client('sqs')
s3_client = boto3.resource('s3')
firehose_client = boto3.client('firehose')
debug = os.getenv('DEBUG', False) in (True, 'True')
################################################################################################################
#   Config
################################################################################################################


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

    message_body = message['body']
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

def process_lambda_sqs_record(record):
    ################################################################################################################
    #   Unpack the message from SQS and get bucket name and object name
    ################################################################################################################
    if debug:
        print("\nrecord = {0}".format(record))
        print("\ntype(record) = {0}\n".format(type(record)))

    record_body = record['body']
    if debug:
        print("\nrecord_body = {0}".format(record_body))
        print("\ntype(record_body) = {0}\n".format(type(record_body)))

    record_body_dict = json.loads(record_body)
    if debug:
        print("\nrecord_body_dict = {0}".format(record_body_dict))
        print("\ntype(record_body_dict) = {0}\n".format(type(record_body_dict)))

    message_within_record_body_str = record_body_dict['Message']
    if debug:
        print("\nmessage_within_record_body_str = {0}".format(message_within_record_body_str))
        print("\ntype(message_within_record_body_str) = {0}\n".format(type(message_within_record_body_str)))

    message_within_record_body = json.loads(message_within_record_body_str)
    if debug:
        print("\nmessage_within_record_body = {0}".format(message_within_record_body))
        print("\ntype(message_within_record_body) = {0}\n".format(type(message_within_record_body)))

    s3_notification_records = message_within_record_body['Records']

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


def convert_and_save_json():
    ################################################################################################################
    #   Convert and Save the data from S3 in JSON format
    ################################################################################################################
    df = pd.read_csv(file_path, sep=' ', names=[ 'Bucket Owner', 'Bucket', 'Time', 'Time - Offset', 'Remote IP', 'Requester ARN/Canonical ID','Request ID','Operation', 'Key', 'Request-URI', 'HTTP status', 'Error Code', 'Bytes Sent', 'Object Size','Total Time','Turn-Around Time', 'Referrer', 'User-Agent', 'Version Id', 'Host Id', 'Signature Version','Cipher Suite','Authentication Type', 'Host Header', 'TLS version'],usecols=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24])
    df.to_json(file_path, orient='records')

    with open(file_path, 'r') as f:
        json_data = json.load(f)

    if debug:
        print("\n\nDISPLAY CREATED JSON FILE CONTENTS")
        print(json_data)

    return json_data


def put_object_in_kinesis_firehose_stream(json_data_from_local_file):
    ################################################################################################################
    #   for each object, Put records into the Firehose stream
    ################################################################################################################    
    for json_data in json_data_from_local_file:

        # Fix Time for Elasticsearch
        Time = json_data['Time']
        # TimeOffset = json_data['Time - Offset']
        json_data['TimeForElasticSearch'] = get_elasticsearch_time(Time)

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

        record_string = json.dumps(json_data)
        encoded_record = record_string.encode("ascii")

        # Put the record into the Firehose stream
        try:
            result = firehose_client.put_record(DeliveryStreamName=firehose_name, Record={'Data': encoded_record})
            # time.sleep(0.1)
            if debug:
                print('\nSUCCESS: SENDING into the Firehose one at a time')
        except ClientError as e:
            print('\nFAILED: SENDING into the Firehose one at a time\n')
            print(e)
            exit(1)

    print("COMPLETED: Putting {0} records into the Firehose one at a time".format( len(json_data_from_local_file) ))


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
                json_data_from_local_file = convert_and_save_json()
                put_object_in_kinesis_firehose_stream(json_data_from_local_file)
            except:
                print("Failed to process Message: {0}".format(Message) )
    else:   #RUNNING A LAMBDA INVOCATION
        for Record in event['Records']:
            try:
                retrieve_s3_file(Record)
                json_data_from_local_file = convert_and_save_json()
                put_object_in_kinesis_firehose_stream(json_data_from_local_file)
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



