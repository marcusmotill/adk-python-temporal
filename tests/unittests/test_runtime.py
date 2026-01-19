# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Unit tests for the runtime module."""

import time
import uuid
import unittest
from unittest.mock import MagicMock, patch

from google.adk import runtime


class TestRuntime(unittest.TestCase):

    def tearDown(self):
        # Reset providers to default after each test
        runtime.set_time_provider(time.time)
        runtime.set_id_provider(lambda: str(uuid.uuid4()))

    def test_default_time_provider(self):
        # Verify it returns a float that is close to now
        now = time.time()
        rt_time = runtime.get_time()
        self.assertIsInstance(rt_time, float)
        self.assertAlmostEqual(rt_time, now, delta=1.0)

    def test_default_id_provider(self):
        # Verify it returns a string uuid
        uid = runtime.new_uuid()
        self.assertIsInstance(uid, str)
        # Should be parseable as uuid
        uuid.UUID(uid)

    def test_custom_time_provider(self):
        # Test override
        mock_time = 123456789.0
        runtime.set_time_provider(lambda: mock_time)
        self.assertEqual(runtime.get_time(), mock_time)

    def test_custom_id_provider(self):
        # Test override
        mock_id = "test-id-123"
        runtime.set_id_provider(lambda: mock_id)
        self.assertEqual(runtime.new_uuid(), mock_id)
