# serverless-acm-manager

A serverless application to manage your AWS ACM certificates for you.

## Installation

Install and configure Serverless: https://www.serverless.com/framework/docs/getting-started/

## How it works
This serverless application reads domains from files stored in an S3 bucket and creates one ACM certificate for each file.
The key of the object used in S3 is also used to store an SSM parameter containing the ARN of the latest available certificate corresponding to a file.

For example, if the following file is added to S3 with the key `/mybrand/domains1.txt`:
```
domain1.com
www.domain1.com
secure.domain1.com
```

This would result in an ACM certificate being created. After all domains are validated, this application takes care to create an SSM parameter with the ARN of the validated certificate. The name of the parameter created is the same as the object key without extension and prepended with /certifier. In the current example, that would be `/certifier/mybrand/domains1`.

If you update this file in S3, a new certificate will be created - once all domains of the new certificate are validated, the old one is deleted and the SSM parameter is updated.

### TL;DR
Upload a file with a list of domains to S3. This application will request a certificate with the specified domains and create an SSM parameter with the name of the file containing the certificate ARN so you can easily refer to it in Terraform or Cloudformation.

## Deploy

### Single region
To deploy the application to a single region, first [create an S3 bucket](https://docs.aws.amazon.com/AmazonS3/latest/gsg/CreatingABucket.html) on the region where you want to deploy and then run:
```bash
serverless deploy --certificates-bucket MYBUCKETNAME --region MYREGION
```
Replacing MYBUCKETNAME and MYREGION with the name of the bucket you created and the region you wish to deploy to (the bucket and the deployment regions must be the same).

### Multi-region
To reduce the overhead of managing the same content for multiple S3 buckets, it's recommended to choose one region as the primary region on which files will be created and deleted and replicate this bucket to buckets in other regions as required. Make sure to enable the replication of delete markers as well. All buckets will also require versioning to be enabled.

For example, if you need the same certificates to be created on eu-central-1 and us-east-1, pick a region to be the primary region. In this case, we'll use us-east-1.

Create your primary bucket on us-east-1 and enable versioning (Requires [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html)):
```bash
aws --region us-east-1 s3 mb s3://my-certificate-bucket-on-us-east-1
aws s3api put-bucket-versioning --bucket my-certificate-bucket-on-us-east-1 --versioning-configuration Status=Enabled
```
Do the same on the second region (in this case, eu-central-1):
```bash
aws --region eu-central-1 s3 mb s3://my-certificate-bucket-on-eu-central-1
aws s3api put-bucket-versioning --bucket my-certificate-bucket-on-eu-central-1 --versioning-configuration Status=Enabled
```

Create the IAM role for the replication:
```bash
aws iam create-role --role-name certificates-bucket-replication --assume-role-policy-document '{
   "Version":"2012-10-17",
   "Statement":[
      {
         "Effect":"Allow",
         "Principal":{
            "Service":"s3.amazonaws.com"
         },
         "Action":"sts:AssumeRole"
      }
   ]
}'
```

Create the IAM Policy for the replication - make sure the bucket names match in the "Resource" sections of the policy.

If you have more than one bucket configured for replication, you can specify multiple Resource keys (see [Setting up permissions for replication](https://docs.aws.amazon.com/AmazonS3/latest/dev/setting-repl-config-perm-overview.html)).

Copy the ARN from the output of this command, it'll be needed later.
```bash
aws iam create-policy --policy-name certificates-bucket-replication --policy-document '{
   "Version":"2012-10-17",
   "Statement":[
      {
         "Effect":"Allow",
         "Action":[
            "s3:GetReplicationConfiguration",
            "s3:ListBucket"
         ],
         "Resource":[
            "arn:aws:s3:::my-certificate-bucket-on-us-east-1"
         ]
      },
      {
         "Effect":"Allow",
         "Action":[

            "s3:GetObjectVersion",
            "s3:GetObjectVersionAcl",
            "s3:GetObjectVersionTagging"

         ],
         "Resource":[
            "arn:aws:s3:::my-certificate-bucket-on-us-east-1/*"
         ]
      },
      {
         "Effect":"Allow",
         "Action":[
            "s3:ReplicateObject",
            "s3:ReplicateDelete",
            "s3:ReplicateTags"
         ],
         "Resource":"arn:aws:s3:::my-certificate-bucket-on-eu-central-1/*"
      }
   ]
}'
```

Attach the policy to the IAM role. Make sure to use the appropriate role name and policy ARN, the latter coming from the output of the previous command.
```bash
aws iam attach-role-policy --role-name certificates-bucket-replication --policy-arn POLICY_ARN
```

Configure replication on the primary bucket (Replace "ACCOUNT" with your AWS account number, which you can check with the command `aws sts get-caller-identity`):
```bash
aws s3api put-bucket-replication --bucket my-certificate-bucket-on-us-east-1 --replication-configuration '{
  "Role":"arn:aws:iam::ACCOUNT:role/certificates-bucket-replication",
  "Rules":[
    {
      "Status":"Enabled",
      "Priority":1,
      "Filter": {"Prefix": ""},
      "DeleteMarkerReplication":{
        "Status":"Enabled"
      },
      "Destination":{
        "Bucket":"arn:aws:s3:::my-certificate-bucket-on-eu-central-1"
      }
    }
  ]
}
'
```

Once all the buckets are in place, you can deploy the lambda functions:
```bash
serverless deploy --certificates-bucket my-certificate-bucket-on-us-east-1 --region my-certificate-bucket-on-us-east-1
serverless deploy --certificates-bucket my-certificate-bucket-on-eu-central-1 --region my-certificate-bucket-on-eu-central-1
```

Make sure to only add and delete objects on the primary bucket!

