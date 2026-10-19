#!/usr/bin/env python3

import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock


fake_boto3 = types.ModuleType("boto3")
fake_session = Mock()
fake_session.client.side_effect = lambda service_name: Mock()
fake_session.resource.return_value = Mock()
fake_boto3.Session = Mock(return_value=fake_session)
fake_boto3.resource = Mock(return_value=Mock())
sys.modules["boto3"] = fake_boto3
sys.path.insert(0, str(Path(__file__).parent))

import ec2_auto_register as auto_register
import ec2_scheduler_dynamo as scheduler


class DynamoSchedulerTests(unittest.TestCase):
    def setUp(self):
        scheduler.table = MagicMock()
        scheduler.ec2 = Mock()
        scheduler.ec2.stop_instances.return_value = {}
        scheduler.ec2.start_instances.return_value = {}
        scheduler.cloudwatch = Mock()
        auto_register.table = Mock()

    def test_stop_flow_reads_active_records_and_updates_them(self):
        scheduler.table.scan.return_value = {
            "Items": [{"InstanceId": "i-mock123"}]
        }
        scheduler.ec2.describe_instances.return_value = {
            "Reservations": [{"Instances": [{"InstanceId": "i-mock123"}]}]
        }
        batch_writer = scheduler.table.batch_writer.return_value.__enter__.return_value

        response = scheduler.lambda_handler({"detail": {"accion": "stop"}}, None)

        scheduler.table.scan.assert_called_once()
        scheduler.ec2.stop_instances.assert_called_once_with(InstanceIds=["i-mock123"])
        batch_writer.put_item.assert_called_once()
        scheduler.cloudwatch.put_metric_data.assert_called_once()
        body = json.loads(response["body"])
        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(body["data"]["instances_processed"], 1)
        self.assertEqual(body["data"]["results"]["success"], 1)
        self.assertEqual(batch_writer.put_item.call_args.kwargs["Item"]["LastAction"], "stop")

    def test_auto_registers_instances_from_run_instances_event(self):
        event = {
            "detail": {
                "eventSource": "ec2.amazonaws.com",
                "eventName": "RunInstances",
                "responseElements": {
                    "instancesSet": {"items": [{"instanceId": "i-new123"}]}
                },
            }
        }

        response = auto_register.lambda_handler(event, None)

        auto_register.table.put_item.assert_called_once()
        item = auto_register.table.put_item.call_args.kwargs["Item"]
        self.assertEqual(item["InstanceId"], "i-new123")
        self.assertEqual(item["Status"], "active")
        self.assertEqual(response["statusCode"], 200)

    def test_ignores_non_run_instances_events(self):
        response = auto_register.lambda_handler(
            {"detail": {"eventSource": "ec2.amazonaws.com", "eventName": "StopInstances"}},
            None,
        )

        self.assertEqual(response["statusCode"], 400)
        auto_register.table.put_item.assert_not_called()


if __name__ == "__main__":
    unittest.main()