import json
import time
from pathlib import Path
from datetime import datetime
from botocore.exceptions import ClientError
from colorama import init, Fore, Style

availability_zone = 'a'
secret_searcher_role_name = 'minimal-ssm'
tags = [{'Key': 'usage', 'Value': 'CloudQuarry'}]
devices = ['/dev/sdf',
           '/dev/sdg',
           '/dev/sdh',
           '/dev/sdi',
           '/dev/sdj',
           '/dev/sdk',
           '/dev/sdl',
           '/dev/sdm',
           '/dev/sdn',
           '/dev/sdo',
           '/dev/sdp']

# list of objects of the form {'/dev/sdf':'ami-123456'} to keep track of what device in use
in_use_devices = {}
s3_bucket_name = ''
s3_bucket_region = ''
scanning_script_name = 'mount_and_dig.sh'
install_ntfs_3g_script_name = 'install_ntfs_3g.sh'
boto3_session = None

def get_ami(ami_id, region):
    try:
        log_success(f'Retrieving the data for AMI {ami_id} from region {region} (search is performed through deprecated AMIs as well)')
        ec2_client = boto3_session.client('ec2', region_name=region)
        
        response = ec2_client.describe_images(
            ImageIds=[ami_id],
            IncludeDeprecated=True  # This allows searching through deprecated AMIs as well
        )
        
        # Check if any images were returned
        if len(response['Images']) > 0:
            ami = response['Images'][0]
            log_success(f"AMI {ami_id} found in region {region}")
            log_success(f"AMI JSON Object: {ami}")
            return ami
        else:
            log_error(f"AMI {ami_id} not found in region {region}. Exiting...")
            cleanup(region)
            exit()
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        if error_code == 'InvalidAMIID.Malformed':
            log_error(f"Invalid AMI ID format: {ami_id}. Exiting...")
        elif error_code == 'InvalidAMIID.NotFound':
            log_error(f"AMI {ami_id} not found in region {region}. Exiting...")
        else:
            log_error(f"Unexpected error: {error_message}. Exiting...")

        cleanup(region)
        exit()


def create_s3_bucket(region):
    log_success(f'Checking if S3 bucket {s3_bucket_name} exists...')
    s3 = boto3_session.client('s3')
    buckets = s3.list_buckets()['Buckets']

    for bucket in buckets:
        if bucket['Name'] == s3_bucket_name:
            log_success(f'Bucket {s3_bucket_name} exists in current AWS account')
            set_bucket_region(s3_bucket_name)
            return
    
    try:
        log_warning('Bucket not found. Creating...')
        response = s3.create_bucket(Bucket=s3_bucket_name, CreateBucketConfiguration={'LocationConstraint': region})
        log_success(f'Bucket created: {response["Location"]}')
        set_bucket_region(s3_bucket_name)
    except  ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'BucketAlreadyExists':
            log_error(f'Bucket {s3_bucket_name} already exists and is owned by somebody else. Please modify the bucket name and run the script again.')
            cleanup(region)
            exit()
        else:
            log_error('Unknown error occurred. Execution might continue as expected...')


def set_bucket_region(bucket_name):
    s3 = boto3_session.client('s3')
    
    try:
        response = s3.get_bucket_location(Bucket=bucket_name)
        region = response['LocationConstraint']
        
        # AWS returns None for buckets in us-east-1 instead of 'us-east-1'
        global s3_bucket_region
        s3_bucket_region = region if region else 'us-east-1'
    
    except Exception as e:
        log_error(f"An error occurred: {e}")
        return None

def upload_script_to_bucket(script_name):
    log_success(f'Checking if script {script_name} is already inside the bucket {s3_bucket_name}...')
    s3 = boto3_session.client('s3', region_name=s3_bucket_region)
    response = s3.list_objects_v2(Bucket=s3_bucket_name, Prefix=script_name)

    if 'Contents' in response:
        log_success(f'Script found')
        return
    
    log_warning(f'Script {script_name} not found in bucket {s3_bucket_name}. Uploading...')

    base_path = Path(__file__).parent
    
    f = open(f'{base_path}\\bash_scripts\\{script_name}')
    script = f.read()
    f.close()

    s3.put_object(Bucket=s3_bucket_name, Body=script, Key=script_name)
    log_success(f'Script {script_name} uploaded in bucket {s3_bucket_name}')


def get_instance_profile_secret_searcher(region):
    iam = boto3_session.client('iam')
    log_success(f'Checking if role {secret_searcher_role_name} for Secret Searcher instance exists')

    try:
        response = iam.get_role(RoleName=secret_searcher_role_name)

        log_success(f'Role {response["Role"]["Arn"]} was found')
    except ClientError as e:
        if e.response['Error']['Code'] != 'NoSuchEntity':
            log_error(f'Unknown error: {e["Error"]["Code"]}. Exiting...')
            cleanup(region)
            exit()
        
        log_warning('Role doesn\'t exist. Creating...')
        response = iam.create_role(RoleName=secret_searcher_role_name, AssumeRolePolicyDocument=
        """{
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {
                        "Service": "ec2.amazonaws.com"
                    },
                    "Action": "sts:AssumeRole"
                }
            ]
        }""", Tags=tags)

        iam.attach_role_policy(RoleName=secret_searcher_role_name, PolicyArn='arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore')
        iam.attach_role_policy(RoleName=secret_searcher_role_name, PolicyArn='arn:aws:iam::aws:policy/AmazonS3FullAccess')

        log_success(f'Role {response["Role"]["Arn"]} created and policy configured')

    try:
        log_success(f'Checking if instance profile {secret_searcher_role_name} exists')
        response = iam.get_instance_profile(InstanceProfileName=secret_searcher_role_name)
        log_success(f'Instance profile found: {response["InstanceProfile"]["Arn"]}')

        return response["InstanceProfile"]["Arn"]
    except ClientError as e:
        log_warning('Instance profile not found')

        if e.response['Error']['Code'] != 'NoSuchEntity':
            log_error(f'Unknown error: {e["Error"]["Code"]}. Exiting...')
            cleanup(region)
            exit()
        
        log_warning('Creating instance profile...')
        response = iam.create_instance_profile(InstanceProfileName=secret_searcher_role_name, Tags=tags)
        iam.add_role_to_instance_profile(InstanceProfileName=secret_searcher_role_name, RoleName=secret_searcher_role_name)

        log_success(f'Created instance profile {response["InstanceProfile"]["Arn"]}')
        log_success('Waiting 1 min for the instance profile to be fully available in AWS')
        time.sleep(60)

        return response["InstanceProfile"]["Arn"]
        

def wait_for_instance_status(instance_id, desired_status, region):
    log_success(f'Checking instance status every 2s until the instance has status \'{desired_status}\'')
    
    ec2 = boto3_session.client('ec2', region)
    status_reached = False
    
    while status_reached == False:
        instance = ec2.describe_instances(InstanceIds=[instance_id])
        status_reached = instance['Reservations'][0]['Instances'][0]['State']['Name']  == desired_status
        
        if status_reached == False:
            time.sleep(2)
    
    log_success(f'Instance {instance_id} reached the status \'{desired_status}\'')


def create_secret_searcher(region, instance_profile_arn):
    ec2 = boto3_session.client('ec2', region)

    log_success('Checking if a secret searcher is already running in this region...')
    instances = ec2.describe_instances(Filters=[{'Name':'tag-key', 'Values':['usage']},
                                                {'Name':'tag-value','Values':['SecretSearcher']},
                                                {'Name':'instance-state-name', 'Values':['pending','running']}])

    if len(instances['Reservations']) > 0:
        instance_id = instances['Reservations'][0]['Instances'][0]['InstanceId']

        log_success(f'Secret searcher found: {instance_id}')
        log_success(f"Checking and waiting the instance to be in 'running' state")

        wait_for_instance_status(instance_id, 'running', region)

        log_success(f'Secret searcher is ready and running in this region')
        return instance_id

    log_warning('No secret searcher instance found. Starting creation process...')
    log_success('Getting AMI for latest Amazon Linux 202* for current region...')

    response = ec2.describe_images(Filters=[{'Name':'name','Values':['al202*-ami-202*-x86_64']}],
                                     Owners=['amazon'])

    sorted_images = sorted(
            response['Images'],
            key=lambda x: datetime.strptime(x['CreationDate'], '%Y-%m-%dT%H:%M:%S.%fZ'),
            reverse=True
        )

    amazon_ami_id = sorted_images[0]['ImageId']

    log_success(f'Creating Secret Searcher instance based on official and most recent Amazon Image AMI {amazon_ami_id}...')
    secret_searcher_instance = ec2.run_instances(InstanceType='c5.large',
                            Placement={'AvailabilityZone':f'{region}{availability_zone}'},
                            IamInstanceProfile ={'Arn':instance_profile_arn},
                            ImageId=amazon_ami_id,
                            MinCount=1,
                            MaxCount=1,
                            BlockDeviceMappings=[{'DeviceName':'/dev/xvda', 'Ebs': {'VolumeSize': 50}}],
                            TagSpecifications=[{'ResourceType': 'instance', 'Tags':[{'Key': 'usage', 'Value': 'SecretSearcher'}]}])
    
    instance_id = secret_searcher_instance['Instances'][0]['InstanceId']
    log_success(f"Secret Searcher instance {instance_id} created. Waiting for instance to be in 'running' state...")
    
    wait_for_instance_status(instance_id, 'running', region)
    log_success('Waiting 1 more min for the instance to start SSM Agent')
    time.sleep(60)

    return instance_id


def install_searching_tools(instance_id, region, is_windows=False):
    log_success(f'Installing tools on Secret Searcher instance {instance_id} for searching secrets...')
    ssm = boto3_session.client('ssm', region)
    
    # Download the script at /home/ec2-user/ and execute it
    if is_windows:
        command = ssm.send_command(InstanceIds=[instance_id],
                                DocumentName='AWS-RunRemoteScript',
                                Parameters={
                                    'sourceType': ['S3'],
                                    'sourceInfo': [f'{{"path":"https://{s3_bucket_name}.s3.{s3_bucket_region}.amazonaws.com/{install_ntfs_3g_script_name}"}}'],
                                    'commandLine': [f'bash /home/ec2-user/{install_ntfs_3g_script_name}'],
                                    'workingDirectory': ['/home/ec2-user/']
                                    })
        
        log_success('Installation started. Waiting for completion...')
        waiter = ssm.get_waiter('command_executed')
        waiter.wait(CommandId=command['Command']['CommandId'], InstanceId=instance_id, WaiterConfig={'Delay':15, 'MaxAttempts':60})

        output = ssm.get_command_invocation(CommandId=command['Command']['CommandId'], InstanceId=instance_id)
        log_success(f'Command execution finished with status: {output["Status"]}')

        if output['Status'] != 'Success':
            log_error(f'Installation failed. Please check what went wrong or install it manually and disable this step. Exiting...')
            cleanup()
            exit()

    log_success(f'Copying {scanning_script_name} from S3 bucket {s3_bucket_name} to Secret Searcher instance {instance_id} using SSM...')
    bash_command = f"if test -f /home/ec2-user/{scanning_script_name}; then echo '[INFO] Script already present on disk';else aws --region {s3_bucket_region} s3 cp s3://{s3_bucket_name}/{scanning_script_name} /home/ec2-user/{scanning_script_name} && chmod +x /home/ec2-user/{scanning_script_name}; fi"
    command = ssm.send_command(InstanceIds=[instance_id],
                            DocumentName='AWS-RunShellScript',
                            Parameters={'commands':[bash_command]})
    
    waiter = ssm.get_waiter('command_executed')
    waiter.wait(CommandId=command['Command']['CommandId'], InstanceId=instance_id)

    output = ssm.get_command_invocation(CommandId=command['Command']['CommandId'], InstanceId=instance_id)
    log_success(f'Command execution finished with status: {output["Status"]}')


def get_targets(region, os='all'):
    f = open('targets.json')
    all_amis = json.loads(f.read())
    f.close()
    
    targets = [x for x in all_amis if x['Region'] == region]
    
    if os == 'all':
        return targets

    if os == 'linux':
        linux_targets = [x for x in targets if 'Platform' not in x]
        return linux_targets
    
    if os == 'windows':
        windows_targets = [x for x in targets if 'Platform' in x]
        return windows_targets

def start_instance_with_target_ami(ami_object, region, is_ena=False):
    ec2 = boto3_session.client('ec2', region)
    log_success(f"Starting EC2 instance for AMI {ami_object['ImageId']}...")

    try:
        instance_type = 'c5.large'
        if 'VirtualizationType' in ami_object and ami_object['VirtualizationType'] == 'paravirtual':
            log_warning('VirtualizationType is paravirtual. Instance type will be changed from c5.large to c3.large')
            instance_type = 'c3.large'
        elif is_ena:
            log_warning('ENA support is required. Instance type will be changed from c5.large to t2.medium and will have a public IP address.')
            instance_type = 't2.medium'
        
        instance = None
        if is_ena == False:
            instance = ec2.run_instances(InstanceType=instance_type,
                                    Placement={'AvailabilityZone':f'{region}{availability_zone}'},
                                    NetworkInterfaces=[{'AssociatePublicIpAddress':False, 'DeviceIndex':0}],
                                    MaxCount=1, MinCount=1,
                                    ImageId=ami_object['ImageId'],
                                    TagSpecifications=[{'ResourceType': 'instance', 'Tags':tags}])
        else:
            instance = ec2.run_instances(InstanceType=instance_type,
                                    Placement={'AvailabilityZone':f'{region}{availability_zone}'},
                                    MaxCount=1, MinCount=1,
                                    ImageId=ami_object['ImageId'],
                                    TagSpecifications=[{'ResourceType': 'instance', 'Tags':tags}])
        
        instance_id = instance['Instances'][0]['InstanceId']
        log_success(f"Instance {instance_id} created. Waiting to be in 'running' state...")

        waiter = ec2.get_waiter('instance_running')
        waiter.wait(InstanceIds=[instance_id], WaiterConfig={'Delay': 5, 'MaxAttempts': 120})

        log_success(f"Instance {instance_id} based on ami {ami_object['ImageId']} is ready")

        return {"instanceId": instance_id, "ami": ami_object['ImageId']}
    except Exception as e:
        error = 'failed '
        if hasattr(e, 'message'):
            error = f'{error}  {e.message}'
        else:
            error = f'{error}  {e}'

        if '(ENA)' in error and is_ena == False:
            log_warning(f'AMI {ami_object["ImageId"]} requires ENA support. Attempting to start the instance again with ENA support compatibility...')
            return start_instance_with_target_ami(ami_object, region, is_ena=True)
        else:
            log_error(f"Something went wrong when launching instance with AMI {ami_object['ImageId']}: {str(e)}")
            log_error("To fix this you might need to edit the script and change the instance type to be compatible with the AMIs requirements. Check instance types here: https://aws.amazon.com/ec2/instance-types/")
            log_error("Script can't resume execution and will exit...")
            cleanup()
            exit()

def stop_instance(instance_ids, region):
    try:
        log_success(f'Stopping EC2 instances {instance_ids}')
        ec2 = boto3_session.client('ec2', region)
        ec2.stop_instances(InstanceIds=instance_ids)

        waiter = ec2.get_waiter('instance_stopped')
        waiter.wait(InstanceIds=instance_ids, WaiterConfig={'Delay':5, 'MaxAttempts':1000})

    except Exception as e:
        log_error(f'Error when stopping instances {instance_ids}. Error: {str(e)}')


def move_volumes_and_terminate_instance(instance_id, instance_id_secret_searcher, ami, region):
    ec2 = boto3_session.client('ec2', region)
    log_success('Starting detaching volumes procedure...')

    volumes = ec2.describe_volumes(Filters=[{'Name':'attachment.instance-id', 'Values':[instance_id]}])
    volume_ids = [x['VolumeId'] for x in volumes['Volumes']]

    if len(devices) < len(volume_ids):
        log_error('Target AMI has more EBS volumes than the number of supported EBS volumes that can be attached to an EC2 instance. This case is not covered by the script. Exiting...')
        exit()

    log_success(f'Volumes to detach: {volume_ids}')

    for volume_id in volume_ids:
        log_success(f'Detaching volume {volume_id}...')
        ec2.detach_volume(VolumeId=volume_id)

    log_success("Waiting for all detached volumes to be in 'available' state...")

    is_available = False
    while is_available == False:
        volumes = ec2.describe_volumes(VolumeIds=volume_ids)
        is_available = all([x['State'] == 'available' for x in volumes['Volumes']])

        if is_available == False:
            time.sleep(5)
    
    log_success("All volumes are in 'available' state")
    
    log_warning(f'Terminating instance {instance_id} created for target AMI...')
    ec2.terminate_instances(InstanceIds=[instance_id])
    log_success('Instance {instance_id} terminated')

    log_success('Moving volumes to secret searching instance...')

    for volume_id in volume_ids:
        device = devices[0]

        log_success(f'Attaching volume {volume_id} as device {device}')
        ec2.attach_volume(Device=device, InstanceId=instance_id_secret_searcher, VolumeId=volume_id)
        
        devices.remove(device)
        in_use_devices[device]=ami

    log_success("Waiting for volumes to be in 'in-use' state...")
    waiter = ec2.get_waiter('volume_in_use')
    waiter.wait(VolumeIds=volume_ids, WaiterConfig={'Delay':3, 'MaxAttempts':60})
    log_success('Volumes are ready to be searched')

    return volume_ids


def start_digging_for_secrets(instance_id_secret_searcher, target_ami, region):
    log_success('Starting digging for secrets...')
    ssm = boto3_session.client('ssm', region)
    volumes = []

    for in_use_device in in_use_devices.keys():
        if target_ami in in_use_devices[in_use_device]:
            volumes.append(in_use_device)

    parameter_volumes = ' '.join(volumes)

    command = ssm.send_command(InstanceIds=[instance_id_secret_searcher],
                        DocumentName='AWS-RunShellScript',
                        Parameters={'commands':[f'/home/ec2-user/{scanning_script_name} {parameter_volumes}']})

    log_success(f'Secret searching in {parameter_volumes} started. Waiting for completion...')

    waiter = ssm.get_waiter('command_executed')
    waiter.wait(CommandId=command['Command']['CommandId'],
                InstanceId=instance_id_secret_searcher,
                WaiterConfig={'Delay':5, 'MaxAttempts':720})
    
    log_success('Scanning completed')


def upload_results(instance_id_secret_searcher, target_ami, region):
    log_success(f'Uploading results for AMI {target_ami} to S3 bucket {s3_bucket_name}...')

    ssm = boto3_session.client('ssm', region)
    command = ssm.send_command(InstanceIds=[instance_id_secret_searcher],
                        DocumentName='AWS-RunShellScript',
                        Parameters={'commands':[f'aws --region {s3_bucket_region} s3 sync /home/ec2-user/OUTPUT/ s3://{s3_bucket_name}/{region}/{target_ami}/', 'rm -rf /home/ec2-user/OUTPUT/']})
    
    log_success(f'Upload started. Waiting for upload to complete (this might take a while)...')
    waiter = ssm.get_waiter('command_executed')
    waiter.wait(CommandId=command['Command']['CommandId'], InstanceId=instance_id_secret_searcher, WaiterConfig={'Delay':5, 'MaxAttempts':800})
    log_success(f'Upload completed')

    
def delete_volumes(volume_ids, region):
    log_success(f'Starting deleting volumes {volume_ids} procedure...')
    ec2 = boto3_session.client('ec2', region)

    log_success(f'Detaching volumes {volume_ids}...')
    for volume_id in volume_ids:
        ec2.detach_volume(VolumeId=volume_id)

    log_success("Waiting volumes to be in 'available' state...")

    waiter = ec2.get_waiter('volume_available')
    waiter.wait(VolumeIds=volume_ids, WaiterConfig={'Delay':3, 'MaxAttempts':80})

    log_warning(f'Deleting volumes {volume_ids}')
    for volume_id in volume_ids:
        ec2.delete_volume(VolumeId=volume_id)
    
    log_warning("All volumes were set for deletion. The script doesn't wait for deletion confirmation. Please check manually if everything was deleted.")


def cleanup(region):
    log_warning('Starting cleanup (the S3 bucket will not be deleted)...')
    ec2 = boto3_session.client('ec2', region)

    log_success('Deleting EC2 secret searcher instance...')
    instances = ec2.describe_instances(Filters=[{'Name':'tag-key', 'Values':['usage']},
                                                {'Name':'tag-value','Values':['SecretSearcher']},
                                                {'Name':'instance-state-name', 'Values':['pending','running']}])

    if len(instances['Reservations']) == 0:
        log_warning('No secret searcher instance found. Continuing with next resource')
    else:
        # should be only one instance, but just to be sure
        instance_ids = [x['InstanceId'] for x in instances['Reservations'][0]['Instances']]
        log_success(f'Terminating instances: {instance_ids}')
        ec2.terminate_instances(InstanceIds=instance_ids)

    iam = boto3_session.client('iam')
    
    log_success('Deleting role and instance profile...')
    try:
        iam.remove_role_from_instance_profile(InstanceProfileName=secret_searcher_role_name, RoleName=secret_searcher_role_name)
        iam.delete_instance_profile(InstanceProfileName=secret_searcher_role_name)
        iam.detach_role_policy(RoleName=secret_searcher_role_name, PolicyArn='arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore')
        iam.detach_role_policy(RoleName=secret_searcher_role_name, PolicyArn='arn:aws:iam::aws:policy/AmazonS3FullAccess')
        iam.delete_role(RoleName=secret_searcher_role_name)
        log_success('Role and instance profile deleted')
    except ClientError as e:
        if e.response['Error']['Code'] != 'NoSuchEntity':
            log_error(f'Unknown error: {e["Error"]["Code"]}. Exiting...')
            exit()
        else:
            log_success(f'No role {secret_searcher_role_name} found.')


init()  # Initialize colorama

def log_success(message):
    print(f"{Fore.GREEN}[INFO]{Style.RESET_ALL} {message}")

def log_warning(message):
    print(f"{Fore.YELLOW}[WARN]{Style.RESET_ALL} {message}")

def log_error(message):
    print(f"{Fore.RED}[ERROR]{Style.RESET_ALL} {message}")

def dig(args, session):
    global boto3_session
    boto3_session = session
    global s3_bucket_name
    s3_bucket_name = args.bucket
    region = args.region
    searched = False
    start_scan_time = time.time()
    volume_ids = []

    try:
        log_warning("If ran in an EC2 instance, make sure it has the required permissions to execute the tool")
        target_ami = get_ami(args.ami_id, region)

        instance_profile_arn_secret_searcher = get_instance_profile_secret_searcher(region)
        instance_id_secret_searcher = create_secret_searcher(region, instance_profile_arn_secret_searcher)
        create_s3_bucket(region)
        upload_script_to_bucket(scanning_script_name)

        is_windows = 'Platform' in target_ami and target_ami['Platform'] == 'windows'
        if is_windows:
            upload_script_to_bucket(install_ntfs_3g_script_name)

        install_searching_tools(instance_id_secret_searcher, region, is_windows)

        instance = start_instance_with_target_ami(target_ami, region)
        stop_instance([instance['instanceId']], region)

        volume_ids = move_volumes_and_terminate_instance(instance['instanceId'], instance_id_secret_searcher, instance['ami'], region)
        start_scan_time = time.time()
        start_digging_for_secrets(instance_id_secret_searcher, instance['ami'], region)
        
        searched = True
        delete_volumes(volume_ids, region)
    except Exception as e:
        log_error(f'Exception occurred for ami {target_ami}')

        log_error(f'Error: {e}')

        if searched == False and len(volume_ids) > 0:
            delete_volumes(volume_ids, region)
        elif len(volume_ids) > 0:
            log_error("An error occurred while deleting the volumes. Please check manually what happened.")
    else:
        upload_results(instance_id_secret_searcher, instance['ami'], region)
        log_success(f"Total duration for ami {target_ami['ImageId']}: {int((time.time() - start_scan_time))} seconds")
        log_success(f'Scan finished. Check results in s3://{s3_bucket_name}')
    finally:
        cleanup(region)
            

if __name__ == '__main__':
    dig()
