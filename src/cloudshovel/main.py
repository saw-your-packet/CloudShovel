import argparse
import boto3
import botocore
from utils.digger import dig, log_error, log_warning

def parse_args():
    parser = argparse.ArgumentParser(description="CloudShovel: Digging for secrets in public AMIs")

    # Positional argument for AMI ID (without a flag)
    parser.add_argument("ami_id", help="AWS AMI ID to launch")

    # Global arguments
    auth_group = parser.add_mutually_exclusive_group()
    auth_group.add_argument("--profile", help="AWS CLI profile name (Default is 'default')", default="default")
    auth_group.add_argument("--access-key", help="AWS Access Key ID (Default profile will be used if access keys not provided)")
    
    parser.add_argument("--secret-key", help="AWS Secret Access Key")
    parser.add_argument("--session-token", help="AWS Session Token (optional)")

    parser.add_argument("--region", help="AWS Region", default="us-east-1")

    parser.add_argument("--bucket", help="S3 Bucket name to upload and download auxiliary scripts (Bucket will be created if doesn't already exist in your account)", required=True)

    return parser.parse_args()


def create_boto3_session(args):
    session_kwargs = {'region_name': args.region}

    if args.profile:
        session_kwargs['profile_name'] = args.profile
    elif args.access_key:
        if not args.secret_key:
            raise ValueError("Secret key must be provided with access key")
        session_kwargs['aws_access_key_id'] = args.access_key
        session_kwargs['aws_secret_access_key'] = args.secret_key
        if args.session_token:
            session_kwargs['aws_session_token'] = args.session_token

    try:
        session = boto3.Session(**session_kwargs)
        # Test the session by making a simple API call
        identity = session.client('sts').get_caller_identity()
        log_warning(f'The script will run using the identity {identity["Arn"]}')
        confirmation = input("Please confirm if you want to continue by typing 'yes' [yes/NO]:")

        if confirmation != 'yes':
            log_warning('The execution will end now. Exiting...')
            exit()

        return session
    except botocore.exceptions.ClientError as e:
        log_error(f"Failed to create boto3 session: {str(e)}")
        exit()


if __name__ == '__main__':
    args = parse_args()

    print(f"AMI ID: {args.ami_id}")
    print(f"Region: {args.region}")
    print(f"Authentication method: { args.secret_key and args.access_key or args.profile}")
    
    session = create_boto3_session(args)
    
    dig(args, session)
    