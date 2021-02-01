from aws_cdk import core
import aws_cdk.aws_secretsmanager as aws_secretsmanager
# import aws_cdk.aws_cloudformation as aws_cloudformation
import aws_cdk.aws_lambda as aws_lambda
# from aws_cdk.core import CustomResource
import aws_cdk.aws_iam as aws_iam
import aws_cdk.aws_s3_notifications as aws_s3_notifications
import aws_cdk.aws_s3 as aws_s3
import aws_cdk.aws_sns as aws_sns
import aws_cdk.aws_sns_subscriptions as aws_sns_subscriptions
import aws_cdk.aws_sqs as aws_sqs
from aws_cdk.aws_lambda_event_sources import SqsEventSource
import aws_cdk.aws_elasticsearch as aws_elasticsearch
import aws_cdk.aws_cognito as aws_cognito
import aws_cdk.aws_elasticloadbalancingv2 as aws_elasticloadbalancingv2
import aws_cdk.aws_ec2 as aws_ec2
import aws_cdk.aws_cloudtrail as aws_cloudtrail
import inspect as inspect



###########################################################################
# References 
###########################################################################
# https://github.com/aws/aws-cdk/issues/7236



class CdkStack(core.Stack):

    def __init__(self, scope: core.Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # The code that defines your stack goes here

        ###########################################################################
        # AWS SECRETS MANAGER - Templated secret 
        ###########################################################################
        # templated_secret = aws_secretsmanager.Secret(self, "TemplatedSecret",
        #     generate_secret_string=aws_secretsmanager.SecretStringGenerator(
        #         secret_string_template= "{\"username\":\"cleanbox\"}",
        #         generate_string_key="password"
        #     )
        # )
        ###########################################################################
        # CUSTOM CLOUDFORMATION RESOURCE 
        ###########################################################################
        # customlambda = aws_lambda.Function(self,'customconfig',
        # handler='customconfig.on_event',
        # runtime=aws_lambda.Runtime.PYTHON_3_7,
        # code=aws_lambda.Code.asset('customconfig'),
        # )

        # customlambda_statement = aws_iam.PolicyStatement(actions=["events:PutRule"], conditions=None, effect=None, not_actions=None, not_principals=None, not_resources=None, principals=None, resources=["*"], sid=None)
        # customlambda.add_to_role_policy(statement=customlambda_statement)

        # my_provider = cr.Provider(self, "MyProvider",
        #     on_event_handler=customlambda,
        #     # is_complete_handler=is_complete, # optional async "waiter"
        #     log_retention=logs.RetentionDays.SIX_MONTHS
        # )

        # CustomResource(self, 'customconfigresource', service_token=my_provider.service_token)


        ###########################################################################
        # AWS LAMBDA FUNCTIONS 
        ###########################################################################
        sqs_to_elastic_cloud = aws_lambda.Function(self,'sqs_to_elastic_cloud',
        handler='sqs_to_elastic_cloud.lambda_handler',
        runtime=aws_lambda.Runtime.PYTHON_3_7,
        code=aws_lambda.Code.asset('sqs_to_elastic_cloud'),
        memory_size=4096,
        timeout=core.Duration.seconds(301)
        )

        sqs_to_elasticsearch_service = aws_lambda.Function(self,'sqs_to_elasticsearch_service',
        handler='sqs_to_elasticsearch_service.lambda_handler',
        runtime=aws_lambda.Runtime.PYTHON_3_7,
        code=aws_lambda.Code.asset('sqs_to_elasticsearch_service'),
        memory_size=4096,
        timeout=core.Duration.seconds(301)
        )
        ###########################################################################
        # AWS LAMBDA FUNCTIONS 
        ###########################################################################


        ###########################################################################
        # AMAZON S3 BUCKETS 
        ###########################################################################
        cloudtrail_log_bucket = aws_s3.Bucket(self, "cloudtrail_log_bucket")


        ###########################################################################
        # LAMBDA SUPPLEMENTAL POLICIES 
        ###########################################################################
        lambda_supplemental_policy_statement = aws_iam.PolicyStatement(
            effect=aws_iam.Effect.ALLOW,
            actions=["s3:Get*","s3:Head*","s3:List*","firehose:*","es:*"],
            resources=["*"]
            )

        sqs_to_elastic_cloud.add_to_role_policy(lambda_supplemental_policy_statement)
        sqs_to_elasticsearch_service.add_to_role_policy(lambda_supplemental_policy_statement)
        ###########################################################################
        # AWS SNS TOPICS 
        ###########################################################################
        cloudtrail_log_topic = aws_sns.Topic(self, "cloudtrail_log_topic")


        ###########################################################################
        # ADD AMAZON S3 BUCKET NOTIFICATIONS
        ###########################################################################
        cloudtrail_log_bucket.add_event_notification(aws_s3.EventType.OBJECT_CREATED, aws_s3_notifications.SnsDestination(cloudtrail_log_topic))


        ###########################################################################
        # AWS SQS QUEUES
        ###########################################################################
        sqs_to_elasticsearch_service_queue_iqueue = aws_sqs.Queue(self, "sqs_to_elasticsearch_service_queue_dlq")
        sqs_to_elasticsearch_service_queue_dlq = aws_sqs.DeadLetterQueue(max_receive_count=10, queue=sqs_to_elasticsearch_service_queue_iqueue)
        sqs_to_elasticsearch_service_queue = aws_sqs.Queue(self, "sqs_to_elasticsearch_service_queue", visibility_timeout=core.Duration.seconds(300), dead_letter_queue=sqs_to_elasticsearch_service_queue_dlq)

        sqs_to_elastic_cloud_queue_iqueue = aws_sqs.Queue(self, "sqs_to_elastic_cloud_queue_dlq")
        sqs_to_elastic_cloud_queue_dlq = aws_sqs.DeadLetterQueue(max_receive_count=10, queue=sqs_to_elastic_cloud_queue_iqueue)
        sqs_to_elastic_cloud_queue = aws_sqs.Queue(self, "sqs_to_elastic_cloud_queue", visibility_timeout=core.Duration.seconds(300), dead_letter_queue=sqs_to_elastic_cloud_queue_dlq)


        ###########################################################################
        # AWS SNS TOPIC SUBSCRIPTIONS
        ###########################################################################
        cloudtrail_log_topic.add_subscription(aws_sns_subscriptions.SqsSubscription(sqs_to_elastic_cloud_queue))
        cloudtrail_log_topic.add_subscription(aws_sns_subscriptions.SqsSubscription(sqs_to_elasticsearch_service_queue))

        
        ###########################################################################
        # AWS LAMBDA SQS EVENT SOURCE
        ###########################################################################
        sqs_to_elastic_cloud.add_event_source(SqsEventSource(sqs_to_elastic_cloud_queue,batch_size=10))
        sqs_to_elasticsearch_service.add_event_source(SqsEventSource(sqs_to_elasticsearch_service_queue,batch_size=10))


        ###########################################################################
        # AWS ELASTICSEARCH DOMAIN
        ###########################################################################

        ###########################################################################
        # AWS ELASTICSEARCH DOMAIN ACCESS POLICY 
        ###########################################################################
        this_aws_account = aws_iam.AccountPrincipal(account_id="012345678912")

        s3_to_elasticsearch_cloudtrail_logs_domain = aws_elasticsearch.Domain(self, "s3-to-elasticsearch-cloudtrail-logs-domain",
            version=aws_elasticsearch.ElasticsearchVersion.V7_1,
            capacity={
                "master_nodes": 3,
                "data_nodes": 4
            },
            ebs={
                "volume_size": 100
            },
            zone_awareness={
                "availability_zone_count": 2
            },
            logging={
                "slow_search_log_enabled": True,
                "app_log_enabled": True,
                "slow_index_log_enabled": True
            }
        )


        ###########################################################################
        # AMAZON COGNITO USER POOL
        ###########################################################################
        s3_to_elasticsearch_user_pool = aws_cognito.UserPool(self, "s3-to-elasticsearch-cloudtrial-logs-pool",
                                                            account_recovery=None, 
                                                            auto_verify=None, 
                                                            custom_attributes=None, 
                                                            email_settings=None, 
                                                            enable_sms_role=None, 
                                                            lambda_triggers=None, 
                                                            mfa=None, 
                                                            mfa_second_factor=None, 
                                                            password_policy=None, 
                                                            self_sign_up_enabled=None, 
                                                            sign_in_aliases=aws_cognito.SignInAliases(email=True, phone=None, preferred_username=None, username=True), 
                                                            sign_in_case_sensitive=None, 
                                                            sms_role=None, 
                                                            sms_role_external_id=None, 
                                                            standard_attributes=None, 
                                                            user_invitation=None, 
                                                            user_pool_name=None, 
                                                            user_verification=None
                                                            )


        sqs_to_elasticsearch_service.add_environment("ELASTICSEARCH_HOST", s3_to_elasticsearch_cloudtrail_logs_domain.domain_endpoint )
        sqs_to_elasticsearch_service.add_environment("QUEUEURL", sqs_to_elasticsearch_service_queue.queue_url )
        sqs_to_elasticsearch_service.add_environment("DEBUG", "False" )

        sqs_to_elastic_cloud.add_environment("ELASTICCLOUD_SECRET_NAME", "-")
        sqs_to_elastic_cloud.add_environment("ELASTIC_CLOUD_ID", "-")
        sqs_to_elastic_cloud.add_environment("ELASTIC_CLOUD_PASSWORD", "-")
        sqs_to_elastic_cloud.add_environment("ELASTIC_CLOUD_USERNAME", "-")
        sqs_to_elastic_cloud.add_environment("QUEUEURL", sqs_to_elastic_cloud_queue.queue_url )
        sqs_to_elastic_cloud.add_environment("DEBUG", "False" )



        ###########################################################################
        # AWS COGNITO USER POOL
        ###########################################################################
        allevents_trail = aws_cloudtrail.Trail(self, "allevents_trail", bucket=cloudtrail_log_bucket, 
                                                                        cloud_watch_log_group=None, 
                                                                        cloud_watch_logs_retention=None, 
                                                                        enable_file_validation=None, 
                                                                        encryption_key=None, 
                                                                        include_global_service_events=None, 
                                                                        is_multi_region_trail=True, 
                                                                        kms_key=None, 
                                                                        management_events=aws_cloudtrail.ReadWriteType("ALL"), 
                                                                        s3_key_prefix=None, 
                                                                        send_to_cloud_watch_logs=False, 
                                                                        sns_topic=None, 
                                                                        trail_name=None)



