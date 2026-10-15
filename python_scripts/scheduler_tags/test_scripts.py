#!/usr/bin/env python3

import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock


fake_boto3 = types.ModuleType("boto3")
fake_session = Mock()
fake_session.client.side_effect = lambda service_name: Mock()
fake_session.resource.return_value = Mock()
fake_boto3.Session = Mock(return_value=fake_session)
fake_boto3.resource = Mock(return_value=Mock())
sys.modules["boto3"] = fake_boto3
sys.path.insert(0, str(Path(__file__).parent))

import ec2_scheduler_tags as scheduler


class TagSchedulerTests(unittest.TestCase):
    def setUp(self):
        scheduler.ec2 = Mock()
        scheduler.cloudwatch = Mock()

    def test_stop_flow_selects_tagged_running_instances_and_emits_metrics(self):
        scheduler.ec2.describe_instances.return_value = {
            "Reservations": [{"Instances": [{"InstanceId": "i-mock123"}]}]
        }

        response = scheduler.lambda_handler({"detail": {"accion": "stop"}}, None)

        scheduler.ec2.describe_instances.assert_called_once_with(
            Filters=[
                {"Name": "instance-state-name", "Values": ["running"]},
                {"Name": "tag:Environment", "Values": scheduler.TAG_VALUES},
            ],
            MaxResults=100,
        )
        scheduler.ec2.stop_instances.assert_called_once_with(InstanceIds=["i-mock123"])
        scheduler.cloudwatch.put_metric_data.assert_called_once()
        body = json.loads(response["body"])
        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(body["data"]["instances_list"], ["i-mock123"])
        self.assertEqual(body["data"]["results"]["success"], 1)

    def test_rejects_unknown_action_without_calling_aws(self):
        response = scheduler.lambda_handler({"detail": {"accion": "reboot"}}, None)

        self.assertEqual(response["statusCode"], 400)
        scheduler.ec2.describe_instances.assert_not_called()
        scheduler.ec2.stop_instances.assert_not_called()
        scheduler.ec2.start_instances.assert_not_called()


if __name__ == "__main__":
    unittest.main()