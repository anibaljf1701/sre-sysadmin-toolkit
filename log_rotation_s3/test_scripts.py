#!/usr/bin/env python3

import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path


SCRIPT = Path(__file__).with_name("log_rotation_s3.sh")


class LogRotationTests(unittest.TestCase):
    def run_rotation(self, threshold, weekly_day):
        temporary_directory = tempfile.TemporaryDirectory()
        root = Path(temporary_directory.name)
        log_dir = root / "logs"
        fake_bin = root / "bin"
        log_dir.mkdir()
        fake_bin.mkdir()

        old_log = log_dir / "application.log"
        old_log.write_text("mock log data\n", encoding="utf-8")
        old_time = (datetime.now() - timedelta(days=2)).timestamp()
        os.utime(old_log, (old_time, old_time))

        aws_log = root / "aws-commands.log"
        fake_aws = fake_bin / "aws"
        fake_aws.write_text(
            "#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> \"$AWS_MOCK_LOG\"\n",
            encoding="utf-8",
        )
        fake_aws.chmod(0o755)

        env = os.environ.copy()
        env.update(
            {
                "PATH": f"{fake_bin}{os.pathsep}{env['PATH']}",
                "AWS_MOCK_LOG": str(aws_log),
                "LOG_DIR": str(log_dir),
                "S3_BUCKET": "s3://mock-bucket/logs",
                "AWS_REGION": "us-east-1",
                "FILE_THRESHOLD": str(threshold),
                "WEEKLY_ROTATION_DAY": str(weekly_day),
            }
        )

        result = subprocess.run(
            ["bash", str(SCRIPT)],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        return temporary_directory, old_log, aws_log, result

    def test_uploads_archive_and_removes_old_logs_after_success(self):
        today = datetime.now().isoweekday()
        temporary_directory, old_log, aws_log, result = self.run_rotation(1, today)
        with temporary_directory:
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(old_log.exists())
            self.assertIn("s3 cp", aws_log.read_text(encoding="utf-8"))
            self.assertIn("s3://mock-bucket/logs/", aws_log.read_text(encoding="utf-8"))

    def test_does_not_upload_when_threshold_and_weekday_do_not_match(self):
        today = datetime.now().isoweekday()
        other_day = 1 if today != 1 else 2
        temporary_directory, old_log, aws_log, result = self.run_rotation(99, other_day)
        with temporary_directory:
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(old_log.exists())
            self.assertFalse(aws_log.exists())


if __name__ == "__main__":
    unittest.main()