"""Tensorboard summaries for the single graph AdaNet implementation.

Copyright 2018 The AdaNet Authors. All Rights Reserved.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    https://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import abc

import tensorflow as tf


class Summary(object):
  """Interface for writing summaries to Tensorboard."""

  __metaclass__ = abc.ABCMeta

  @abc.abstractmethod
  def scalar(self, name, tensor, family=None):
    """Outputs a `tf.Summary` protocol buffer containing a single scalar value.

    The generated tf.Summary has a Tensor.proto containing the input Tensor.

    Args:
      name: A name for the generated node. Will also serve as the series name in
        TensorBoard.
      tensor: A real numeric Tensor containing a single value.
      family: Optional; if provided, used as the prefix of the summary tag name,
        which controls the tab name used for display on Tensorboard.

    Returns:
      A scalar `Tensor` of type `string`. Which contains a `tf.Summary`
      protobuf.

    Raises:
      ValueError: If tensor has the wrong shape or type.
    """

  @abc.abstractmethod
  def image(self, name, tensor, max_outputs=3, family=None):
    """Outputs a `tf.Summary` protocol buffer with images.

    The summary has up to `max_outputs` summary values containing images. The
    images are built from `tensor` which must be 4-D with shape `[batch_size,
    height, width, channels]` and where `channels` can be:

    *  1: `tensor` is interpreted as Grayscale.
    *  3: `tensor` is interpreted as RGB.
    *  4: `tensor` is interpreted as RGBA.

    The images have the same number of channels as the input tensor. For float
    input, the values are normalized one image at a time to fit in the range
    `[0, 255]`.  `uint8` values are unchanged.  The op uses two different
    normalization algorithms:

    *  If the input values are all positive, they are rescaled so the largest
    one
      is 255.

    *  If any input value is negative, the values are shifted so input value 0.0
      is at 127.  They are then rescaled so that either the smallest value is 0,
      or the largest one is 255.

    The `tag` in the outputted tf.Summary.Value protobufs is generated based on
    the
    name, with a suffix depending on the max_outputs setting:

    *  If `max_outputs` is 1, the summary value tag is '*name*/image'.
    *  If `max_outputs` is greater than 1, the summary value tags are
      generated sequentially as '*name*/image/0', '*name*/image/1', etc.

    Args:
      name: A name for the generated node. Will also serve as a series name in
        TensorBoard.
      tensor: A 4-D `uint8` or `float32` `Tensor` of shape `[batch_size, height,
        width, channels]` where `channels` is 1, 3, or 4.
      max_outputs: Max number of batch elements to generate images for.
      family: Optional; if provided, used as the prefix of the summary tag name,
        which controls the tab name used for display on Tensorboard.

    Returns:
      A scalar `Tensor` of type `string`. The serialized `tf.Summary` protocol
      buffer.
    """

  @abc.abstractmethod
  def histogram(self, name, values, family=None):
    """Outputs a `tf.Summary` protocol buffer with a histogram.

    Adding a histogram summary makes it possible to visualize your data's
    distribution in TensorBoard. You can see a detailed explanation of the
    TensorBoard histogram dashboard
    [here](https://www.tensorflow.org/get_started/tensorboard_histograms).

    The generated [`tf.Summary`](
    tensorflow/core/framework/summary.proto)
    has one summary value containing a histogram for `values`.

    This op reports an `InvalidArgument` error if any value is not finite.

    Args:
      name: A name for the generated node. Will also serve as a series name in
        TensorBoard.
      values: A real numeric `Tensor`. Any shape. Values to use to build the
        histogram.
      family: Optional; if provided, used as the prefix of the summary tag name,
        which controls the tab name used for display on Tensorboard.

    Returns:
      A scalar `Tensor` of type `string`. The serialized `tf.Summary` protocol
      buffer.
    """

  @abc.abstractmethod
  def audio(self, name, tensor, sample_rate, max_outputs=3, family=None):
    """Outputs a `tf.Summary` protocol buffer with audio.

    The summary has up to `max_outputs` summary values containing audio. The
    audio is built from `tensor` which must be 3-D with shape `[batch_size,
    frames, channels]` or 2-D with shape `[batch_size, frames]`. The values are
    assumed to be in the range of `[-1.0, 1.0]` with a sample rate of
    `sample_rate`.

    The `tag` in the outputted tf.Summary.Value protobufs is generated based on
    the
    name, with a suffix depending on the max_outputs setting:

    *  If `max_outputs` is 1, the summary value tag is '*name*/audio'.
    *  If `max_outputs` is greater than 1, the summary value tags are
      generated sequentially as '*name*/audio/0', '*name*/audio/1', etc

    Args:
      name: A name for the generated node. Will also serve as a series name in
        TensorBoard.
      tensor: A 3-D `float32` `Tensor` of shape `[batch_size, frames, channels]`
        or a 2-D `float32` `Tensor` of shape `[batch_size, frames]`.
      sample_rate: A Scalar `float32` `Tensor` indicating the sample rate of the
        signal in hertz.
      max_outputs: Max number of batch elements to generate audio for.
      family: Optional; if provided, used as the prefix of the summary tag name,
        which controls the tab name used for display on Tensorboard.

    Returns:
      A scalar `Tensor` of type `string`. The serialized `tf.Summary` protocol
      buffer.
    """


class _ScopedSummary(Summary):
  """Records summaries in a given scope.

  Each scope gets assigned a different collection where summary ops gets added.

  This allows Tensorboard to display summaries with different scopes but the
  same name in the same charts.
  """

  _TMP_COLLECTION_NAME = "_tmp_summaries"

  def __init__(self, scope=None, skip_summary=False):
    """Initializes a `_ScopedSummary`.

    Args:
      scope: String scope name.
      skip_summary: Whether to record summary ops.

    Returns:
      A `_ScopedSummary` instance.
    """

    self._scope = scope
    self._skip_summary = skip_summary

  @property
  def scope(self):
    """Returns scope string."""

    return self._scope

  def _collection_name(self):
    """Returns the collection for recording."""

    if self._scope:
      return "_{}_summaries".format(self._scope)
    return "_global_summaries"

  def _prefix_scope(self, name):
    """Prefixes summary name with scope."""

    if self._scope:
      if name[0] == "/":
        name = name[1:]
      return "{scope}/{name}".format(scope=self._scope, name=name)
    return name

  def scalar(self, name, tensor, family=None):
    """See `Summary`."""

    if self._skip_summary:
      return tf.constant("")

    summary = tf.summary.scalar(
        name=self._prefix_scope(name),
        tensor=tensor,
        family=family,
        collections=[self._TMP_COLLECTION_NAME])
    stripped_summary = self._strip_tag_scope(summary)
    tf.add_to_collection(self._collection_name(), stripped_summary)
    return stripped_summary

  def image(self, name, tensor, max_outputs=3, family=None):
    """See `Summary`."""

    if self._skip_summary:
      return tf.constant("")

    summary = tf.summary.image(
        name=self._prefix_scope(name),
        tensor=tensor,
        max_outputs=max_outputs,
        family=family,
        collections=[self._TMP_COLLECTION_NAME])
    stripped_summary = self._strip_tag_scope(summary)
    tf.add_to_collection(self._collection_name(), stripped_summary)
    return stripped_summary

  def histogram(self, name, values, family=None):
    """See `Summary`."""

    if self._skip_summary:
      return tf.constant("")

    summary = tf.summary.histogram(
        name=self._prefix_scope(name),
        values=values,
        family=family,
        collections=[self._TMP_COLLECTION_NAME])
    stripped_summary = self._strip_tag_scope(summary)
    tf.add_to_collection(self._collection_name(), stripped_summary)
    return stripped_summary

  def audio(self, name, tensor, sample_rate, max_outputs=3, family=None):
    """See `Summary`."""

    if self._skip_summary:
      return tf.constant("")

    summary = tf.summary.audio(
        name=self._prefix_scope(name),
        tensor=tensor,
        sample_rate=sample_rate,
        max_outputs=max_outputs,
        family=family,
        collections=[self._TMP_COLLECTION_NAME])
    stripped_summary = self._strip_tag_scope(summary)
    tf.add_to_collection(self._collection_name(), stripped_summary)
    return stripped_summary

  def _strip_scope(self, name):
    """Returns the name with scope stripped from it."""

    return name.replace("{}/".format(self._scope), "")

  def _strip_tag_scope(self, summary_tensor):
    """Returns a summary `Tensor` with scope stripped from the tag."""

    if not self._scope:
      return summary_tensor

    def _strip_serialized(serialized):
      summ = tf.summary.Summary()
      summ.ParseFromString(serialized)
      summary = summ
      for value in summary.value:
        value.tag = self._strip_scope(value.tag)
      return summary.SerializeToString()

    return tf.py_func(
        _strip_serialized,
        inp=[summary_tensor],
        Tout=tf.string,
        stateful=False,
        name="strip_tag_scope")

  def merge_all(self):
    """Returns a merged summary op."""

    return tf.summary.merge_all(key=self._collection_name())