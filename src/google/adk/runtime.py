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

"""Runtime module for abstracting system primitives like time and UUIDs."""

import time
import uuid
from typing import Callable

_time_provider: Callable[[], float] = time.time
_id_provider: Callable[[], str] = lambda: str(uuid.uuid4())


def set_time_provider(provider: Callable[[], float]) -> None:
  """Sets the provider for the current time.

  Args:
    provider: A callable that returns the current time in seconds since the
      epoch.
  """
  global _time_provider
  _time_provider = provider


def set_id_provider(provider: Callable[[], str]) -> None:
  """Sets the provider for generating unique IDs.

  Args:
    provider: A callable that returns a unique ID string.
  """
  global _id_provider
  _id_provider = provider


def get_time() -> float:
  """Returns the current time in seconds since the epoch."""
  return _time_provider()


def new_uuid() -> str:
  """Returns a new unique ID."""
  return _id_provider()
