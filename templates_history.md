

## Iteration 1

```yaml

AWSTemplateFormatVersion: '2010-09-09'
Description: Serverless API with Lambda, API Gateway HTTP API, IAM Role, and CloudWatch Logs

Resources:

  # --- CloudWatch Log Group (created first, Lambda depends on it) ---
  LambdaLogGroup:
    Type: AWS::Logs::LogGroup
    Properties:
      LogGroupName: !Sub '/aws/lambda/${AWS::StackName}-health-fn'
      RetentionInDays: 7

  # --- IAM Role with least-privilege inline policy ---
  LambdaExecutionRole:
    Type: AWS::IAM::Role
    DependsOn: LambdaLogGroup
    Properties:
      RoleName: !Sub '${AWS::StackName}-lambda-role'
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              Service: lambda.amazonaws.com
            Action: sts:AssumeRole
      Policies:
        - PolicyName: CloudWatchLogsPolicy
          PolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Action:
                  - logs:CreateLogStream
                  - logs:PutLogEvents
                Resource:
                  - !GetAtt LambdaLogGroup.Arn
                  - !Sub '${LambdaLogGroup.Arn}:log-stream:*'

  # --- Lambda Function ---
  HealthFunction:
    Type: AWS::Lambda::Function
    DependsOn: LambdaLogGroup
    Properties:
      FunctionName: !Sub '${AWS::StackName}-health-fn'
      Runtime: python3.13
      Handler: index.handler
      Role: !GetAtt LambdaExecutionRole.Arn
      Code:
        ZipFile: |
          import json

          def handler(event, context):
              return {
                  'statusCode': 200,
                  'headers': {'Content-Type': 'application/json'},
                  'body': json.dumps({'status': 'ok'})
              }

  # --- API Gateway HTTP API ---
  HttpApi:
    Type: AWS::ApiGatewayV2::Api
    Properties:
      Name: !Sub '${AWS::StackName}-http-api'
      ProtocolType: HTTP
      Description: HTTP API for health check endpoint

  # --- Lambda Integration ---
  LambdaIntegration:
    Type: AWS::ApiGatewayV2::Integration
    Properties:
      ApiId: !Ref HttpApi
      IntegrationType: AWS_PROXY
      IntegrationUri: !Sub
        - 'arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31/functions/${LambdaArn}/invocations'
        - LambdaArn: !GetAtt HealthFunction.Arn
      PayloadFormatVersion: '2.0'

  # --- GET /health Route ---
  HealthRoute:
    Type: AWS::ApiGatewayV2::Route
    Properties:
      ApiId: !Ref HttpApi
      RouteKey: 'GET /health'
      Target: !Sub 'integrations/${LambdaIntegration}'

  # --- $default Stage with AutoDeploy ---
  DefaultStage:
    Type: AWS::ApiGatewayV2::Stage
    Properties:
      ApiId: !Ref HttpApi
      StageName: '$default'
      AutoDeploy: true

  # --- Lambda Permission for API Gateway ---
  LambdaApiPermission:
    Type: AWS::Lambda::Permission
    Properties:
      FunctionName: !GetAtt HealthFunction.Arn
      Action: lambda:InvokeFunction
      Principal: apigateway.amazonaws.com
      SourceArn: !Sub 'arn:aws:execute-api:${AWS::Region}:${AWS::AccountId}:${HttpApi}/*/*/health'

Outputs:
  HealthEndpointUrl:
    Description: Invoke URL for the GET /health endpoint
    Value: !Sub 'https://${HttpApi}.execute-api.${AWS::Region}.amazonaws.com/health'

```
