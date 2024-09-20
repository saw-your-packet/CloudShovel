## Introduction

CloudShovel is a tool designed to search for sensitive information within public or private Amazon Machine Images (AMIs). It automates the process of launching instances from target AMIs, mounting their volumes, and scanning for potential secrets or sensitive data.

The tool is a modified version of what was used for the research [AWS CloudQuarry: Digging for Secrets in Public AMIs](https://securitycafe.ro/2024/05/08/aws-cloudquarry-digging-for-secrets-in-public-amis/)

Authors:
- [Eduard Agavriloae](https://www.linkedin.com/in/eduard-k-agavriloae/) - [hacktodef.com](https://hacktodef.com)
- [Matei Josephs](https://www.linkedin.com/in/l31/) - [hivehack.tech](https://hivehack.tech)


**Disclaimer**

> This is not a tool that will fit all scenarios. There will be errors when starting an EC2 instance based on the target AMI or when trying to mount the volumes. We accept pull requests for covering more cases, but our recommendation is to manually try to handle those cases.

Table of Contents:

- [Introduction](#introduction)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
  - [Using pip](#using-pip)
  - [Manually](#manually)
- [Usage](#usage)
- [How It Works](#how-it-works)
- [Customizing scanning](#customizing-scanning)
- [Resources Created](#resources-created)
- [Required Permissions](#required-permissions)
- [Cleaning Up](#cleaning-up)
- [Troubleshooting](#troubleshooting)


## Prerequisites

Before using CloudShovel, ensure you have the following:

- Python 3.6 or higher
- Access to your own AWS account and IAM identity
- Python libraries (can be installed automatically)
  - Boto3 library installed (`pip install boto3`)
  - Colorama library installed (`pip install colorama`)

## Installation

### Using pip
From terminal:

   ```bash
   python3 -m pip install cloudshovel
   ```

### Manually

1. Clone the CloudShovel repository:
   ```
   git clone https://github.com/your-repo/cloudshovel.git
   cd cloudshovel
   ```

2. Install the required Python libraries:
   ```
   pip install -r requirements.txt
   ```

## Usage

To use CloudShovel, run the `main.py` script with the following syntax:

```
cloudshovel <ami_id> --bucket <s3_bucket_name> [--profile <aws_profile> | --access-key <access_key> --secret-key <secret_key> (--session-token <session_token>)] [--region <aws_region>]
```

Arguments:
- `ami_id`: The ID of the AMI you want to scan (required)
- `--bucket`: The name of the S3 bucket to store results (required)
- Authentication with configured AWS CLI profile
  - `--profile`: AWS CLI profile name (default is 'default')
- Authentication with access keys
  - `--access-key`: AWS Access Key ID
  - `--secret-key`: AWS Secret Access Key
  - `--session-token`: AWS Session Token (optional)
- `--region`: AWS region (default is 'us-east-1')

If you don't specify an argument for authentication, the tool will try to automatically use the `default` profile.

Example:
```
cloudshovel ami-1234567890abcdef --bucket my-cloudshovel-results --profile my-aws-profile --region us-west-2
```

## How It Works

CloudShovel operates through the following steps:

1. **Initialization**: 
   - Parses command-line arguments and creates an AWS session.
   - Validates the target AMI's existence.

2. **Setup**:
   - Creates or verifies the existence of the specified S3 bucket.
   - Creates an IAM role and instance profile for the "secret searcher" EC2 instance.
   - Uploads necessary scripts to the S3 bucket.

3. **Secret Searcher Instance**:
   - Launches an EC2 instance (the "secret searcher") based on the latest Amazon Linux 202* AMI.
   - Installs required tools on the secret searcher instance.

4. **Target AMI Processing**:
   - Launches an EC2 instance from the target AMI.
   - Stops the instance and detaches its volumes.
   - Attaches these volumes to the secret searcher instance.

5. **Scanning**:
   - Mounts the attached volumes on the secret searcher instance.
   - Executes the `mount_and_dig.sh` script to search for potential secrets.
   - The script looks for specific file names and patterns that might indicate sensitive information.

6. **Results**:
   - Uploads the scanning results to the specified S3 bucket.

7. **Cleanup**:
   - Detaches and deletes the volumes from the target AMI.
   - Terminates instances and removes created IAM resources.

## Customizing scanning

By default, the tool will execute the next command to search for files and folders that might be of interest: 

```bash
for item in $(find . \( ! -path "./Windows/*" -a ! -path "./Program Files/*" -a ! -path "./Program Files (x86)/*" \) -size -25M \
            \( -name ".aws" -o -name ".ssh" -o -name "credentials.xml" \
            -o -name "secrets.yml" -o -name "config.php" -o -name "_history" \
            -o -name "autologin.conf" -o -name "web.config" -o -name ".env" \
            -o -name ".git" \) -not -empty)
   do
      echo "[+] Found $item. Copying to output..."
      save_name_item=${item:1}
      save_name_item=${save_name_item////\\}
      cp -r $item /home/ec2-user/OUTPUT/$counter/${save_name_item}
   done
```

The full code can be found in `src\cloudshovel\utils\bash_scripts\mount_and_dig.sh`. Feel free to modify the function and search for other files or folders, increase the file size limit or exclude additional folders from the search.

You can also modify the function and replace the usage of `find` with `trufflehog` or `linpeas`. The difference is that using find takes about 1 minute to execute whereas other scanning alternatives might take tens of minutes or hours depending on volume size.

## Resources Created

CloudShovel creates the following AWS resources during its operation:

1. **S3 Bucket**: Stores scanning scripts and results.
2. **IAM Role and Instance Profile**: Named "minimal-ssm", used by the secret searcher instance.
3. **EC2 Instances**:
   - A "secret searcher" instance based on Amazon Linux 2023.
   - A temporary instance launched from the target AMI (terminated after volume detachment).
4. **EBS Volumes**: Temporary attachments to the secret searcher instance (deleted after scanning).

## Required Permissions

To run CloudShovel, your AWS account or IAM identity needs the following permissions:

- EC2:
  - Describe, run, stop, and terminate instances
  - Describe, create, attach, detach, and delete volumes
  - Describe and create tags
- IAM:
  - Create, delete, and manage roles and instance profiles
  - Attach and detach role policies
- S3:
  - Create buckets
  - Put, get, and delete objects
- SSM:
  - Send commands to EC2 instances
  - Get command invocation results

It's recommended to use the principle of least privilege and create a specific IAM user or role for running CloudShovel with only the necessary permissions.

## Cleaning Up

CloudShovel attempts to clean up all created resources after completion or in case of errors. However, it's good practice to verify that all resources have been properly removed, especially:

- Check the EC2 console for any running instances tagged with "usage: CloudQuarry" or "usage: SecretSearcher".
- Verify that the IAM role and instance profile "minimal-ssm" have been deleted.
- The S3 bucket **is not** automatically deleted to preserve results. Delete it manually if no longer needed.

## Troubleshooting

- If the script fails to mount volumes, ensure that the necessary filesystem tools (e.g., ntfs-3g for NTFS volumes) are installed on the secret searcher instance.
- For permission-related errors, verify that your AWS credentials have all the required permissions listed above.
- If experiencing issues with specific AMIs, check their requirements (e.g., virtualization type, ENA support) and adjust the instance types in the script accordingly.

Use this tool responsibly and ensure you have the right to scan the AMIs you're targeting.
