"""An AdaNet ensemble definition in Tensorflow using a single graph.

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

import collections

import tensorflow as tf


class WeightedBaseLearner(
    collections.namedtuple("WeightedBaseLearner",
                           ["weight", "logits", "base_learner"])):
  """An AdaNet weighted base learner.

  A weighted base learner is a weight 'w' applied to a base learner's last layer
  'u'. The results is the base learner's logits, regularized by its complexity.
  """

  def __new__(cls, weight, logits, base_learner):
    """Creates a `WeightedBaseLearner` instance.

    Args:
      weight: The weight `Tensor` to apply to this base learner. The AdaNet
        paper refers to this weight as 'w' in Equations (4), (5), and (6).
      logits: The output `Tensor` after the matrix multiplication of `weight`
        and the base_learner's `last_layer`. The weight's shape is [batch_size,
        logits_dimension]. It is equivalent to a linear logits layer in a neural
        network.
      base_learner: The `BaseLearner` to weight.

    Returns:
      A `WeightedBaseLearner` object.
    """

    return super(WeightedBaseLearner, cls).__new__(
        cls, weight=weight, logits=logits, base_learner=base_learner)


class Ensemble(
    collections.namedtuple("Ensemble", [
        "name",
        "weighted_base_learners",
        "bias",
        "logits",
        "predictions",
        "loss",
        "adanet_loss",
        "complexity_regularized_loss",
        "train_op",
        "complexity_regularization",
        "eval_metric_ops",
        "export_outputs",
    ])):
  """An AdaNet ensemble.

  An ensemble is a collection of base learners which forms a strong learner
  through the weighted sum of their outputs. It is represented by 'f' throughout
  the AdaNet paper. Its component base learners' weights are complexity
  regularized (Gamma) as defined in Equation (4).

  # TODO: Remove fields related to training and evaluation.
  """

  def __new__(cls,
              name,
              weighted_base_learners,
              bias,
              logits,
              predictions,
              loss=None,
              adanet_loss=None,
              complexity_regularized_loss=None,
              train_op=None,
              complexity_regularization=None,
              eval_metric_ops=None,
              export_outputs=None):
    """Creates an `Ensemble` instance.

    Args:
      name: String name of this ensemble. Should be unique in the graph.
      weighted_base_learners: List of `WeightedBaseLearner` instances that form
        this ensemble. Ordered from first to most recent.
      bias: `Tensor` bias vector for the ensemble logits.
      logits: Logits `Tensor`. The result of the function 'f' as defined in
        Section 5.1 which is the sum of the logits of all `WeightedBaseLearner`
        instances in ensemble.
      predictions: Predictions `Tensor` or dict of `Tensor`.
      loss: Loss `Tensor` as defined by the surrogate loss function Phi in
        Equations (4), (5), and (6). Must be either scalar, or with shape `[1]`.
      adanet_loss: Loss `Tensor` as defined by F(w) in Equation (4). Must be
        either scalar, or with shape `[1]`. The AdaNet algorithm aims to
        minimize this objective which balances training loss with the total
        complexity of the base learners in the ensemble.
      complexity_regularized_loss: Loss `Tensor` as defined by F(w,u) in
        Equation (5). Must be either scalar, or with shape `[1]`.
      train_op: Op for the training step.
      complexity_regularization: Complexity regularization `Tensor` of the
        weighted-L1 penalty regularization term in F(w) in Equation (4).
      eval_metric_ops: Dict of metric results keyed by name. The values of the
        dict are the results of calling a metric function, namely a
        `(metric_tensor, update_op)` tuple. `metric_tensor` should be evaluated
        without any impact on state (typically is a pure computation based on
        variables.). For example, it should not trigger the `update_op` or
        require any input fetching.
      export_outputs: Describes the output signatures to be exported to
        `SavedModel` and used during serving.
        A dict `{name: output}` where:
        * name: An arbitrary name for this output.
        * output: an `ExportOutput` object such as `ClassificationOutput`,
            `RegressionOutput`, or `PredictOutput`.
        Single-headed models only need to specify one entry in this dictionary.
        Multi-headed models should specify one entry for each head, one of
        which must be named using
        signature_constants.DEFAULT_SERVING_SIGNATURE_DEF_KEY.

    Returns:
      An `Ensemble` object.
    """

    # TODO: Make weighted_base_learners property a tuple so that
    # `Ensemble` is immutable.
    return super(Ensemble, cls).__new__(
        cls,
        name=name,
        weighted_base_learners=weighted_base_learners,
        bias=bias,
        logits=logits,
        predictions=predictions,
        loss=loss,
        adanet_loss=adanet_loss,
        complexity_regularized_loss=complexity_regularized_loss,
        train_op=train_op,
        complexity_regularization=complexity_regularization,
        eval_metric_ops=eval_metric_ops,
        export_outputs=export_outputs)


class _EnsembleBuilder(object):
  """Builds `Ensemble` instances."""

  def __init__(self, head, adanet_lambda, adanet_beta, use_bias=True):
    """Returns an initialized `_EnsembleBuilder`.

    Args:
      head: A `tf.contrib.estimator.Head` instance.
      adanet_lambda: Float multiplier 'lambda' for applying L1 regularization to
        base learners' mixture weights 'w' in the ensemble proportional to their
        complexity. See Equation (4) in the AdaNet paper.
      adanet_beta: Float L1 regularization multiplier 'beta' to apply equally to
        all base learners' weights 'w' in the ensemble regardless of their
        complexity. See Equation (4) in the AdaNet paper.
      use_bias: Whether to add a bias term to the ensemble's logits.

    Returns:
      An `_EnsembleBuilder` instance.
    """

    self._head = head
    self._adanet_lambda = adanet_lambda
    self._adanet_beta = adanet_beta
    self._use_bias = use_bias

  def append_new_base_learner(self,
                              ensemble,
                              base_learner_builder,
                              summary,
                              features,
                              mode,
                              labels=None):
    """Adds a `BaseLearner` to an `Ensemble` from iteration t-1 for iteration t.

    For iteration t > 0, the ensemble is built given the `Ensemble` for t-1 and
    the new base learner to train as part of the ensemble. The `Ensemble` at
    iteration 0 is comprised of just the base learner.

    The base learner is first given a weight 'w' in a `WeightedBaseLearner`
    which determines its contribution to the ensemble. The base learner's
    complexity L1-regularizes this weight.

    Args:
      ensemble: The recipient `Ensemble` for the `BaseLearner`.
      base_learner_builder: A `adanet.BaseLearnerBuilder` instance which defines
        how to train the base learner and ensemble mixture weights.
      summary: A `_ScopedSummary` instance for recording ensemble summaries.
      features: Input `dict` of `Tensor` objects.
      mode: Estimator's `ModeKeys`.
      labels: Labels `Tensor`, or `dict` of same. Can be None during inference.

    Returns:
      An new `Ensemble` instance with the `BaseLearner` appended.
    """

    with tf.variable_scope("ensemble_{}".format(base_learner_builder.name)):
      weighted_base_learners = []
      iteration = 0
      if ensemble:
        for weighted_base_learner in ensemble.weighted_base_learners:
          with tf.variable_scope("weighted_base_learner_{}".format(iteration)):
            weighted_base_learners.append(
                self._build_weighted_base_learner(
                    weighted_base_learner.base_learner,
                    self._head.logits_dimension,
                    weight_initializer=weighted_base_learner.weight))
          iteration += 1
        bias = self._create_bias(
            self._head.logits_dimension, prior=ensemble.bias)
      else:
        bias = self._create_bias(self._head.logits_dimension)

      with tf.variable_scope("weighted_base_learner_{}".format(iteration)):
        with tf.variable_scope("base_learner"):
          trainable_vars_before = tf.trainable_variables()
          base_learner = base_learner_builder.build_base_learner(
              features=features,
              logits_dimension=self._head.logits_dimension,
              training=mode == tf.estimator.ModeKeys.TRAIN,
              summary=summary,
              previous_ensemble=ensemble)
          trainable_vars_after = tf.trainable_variables()
          var_list = list(
              set(trainable_vars_after) - set(trainable_vars_before))
        weighted_base_learners.append(
            self._build_weighted_base_learner(base_learner,
                                              self._head.logits_dimension))

      return self.build_ensemble(
          name=base_learner_builder.name,
          weighted_base_learners=weighted_base_learners,
          summary=summary,
          bias=bias,
          features=features,
          mode=mode,
          labels=labels,
          base_learner_builder=base_learner_builder,
          var_list=var_list)

  def build_ensemble(self,
                     name,
                     weighted_base_learners,
                     summary,
                     bias,
                     features,
                     mode,
                     labels=None,
                     base_learner_builder=None,
                     var_list=None):
    """Builds an `Ensemble` with the given `WeightedBaseLearner`s.

    Args:
      name: The string name of the ensemble. Typically the name of the builder
        that returned the given `BaseLearner`.
      weighted_base_learners: List of `WeightedBaseLearner` instances that form
        this ensemble. Ordered from first to most recent.
      summary: A `_ScopedSummary` instance for recording ensemble summaries.
      bias: `Tensor` bias vector for the ensemble logits.
      features: Input `dict` of `Tensor` objects.
      mode: Estimator `ModeKeys` indicating training, evaluation, or inference.
      labels: Labels `Tensor`, or `dict` of same. Can be None during inference.
      base_learner_builder: A `adanet.BaseLearnerBuilder` instance which defines
        how to train the base learner and ensemble mixture weights.
      var_list: Optional list or tuple of `Variable` objects to update to
        minimize `loss`.

    Returns:
      An `Ensemble` instance.
    """

    base_learner_logits = []
    ensemble_complexity_regularization = 0
    total_weight_l1_norms = 0
    weights = []
    for weighted_base_learner in weighted_base_learners:
      adanet_gamma = self._adanet_lambda * tf.to_float(
          weighted_base_learner.base_learner.complexity) + self._adanet_beta
      weight_l1_norm = tf.norm(weighted_base_learner.weight, ord=1)
      total_weight_l1_norms += weight_l1_norm
      ensemble_complexity_regularization += adanet_gamma * weight_l1_norm
      base_learner_logits.append(weighted_base_learner.logits)
      weights.append(weight_l1_norm)

    with tf.variable_scope("logits"):
      ensemble_logits = bias
      for logits in base_learner_logits:
        ensemble_logits = tf.add(ensemble_logits, logits)

    with tf.name_scope(""):
      summary.histogram("mixture_weights/adanet/adanet_weighted_ensemble",
                        weights)
      for iteration, weight in enumerate(weights):
        learner = "adanet/adanet_weighted_ensemble/base_learner_{}".format(
            iteration)
        summary.scalar("mixture_weight_norms/{}".format(learner), weight)
        fraction = weight / total_weight_l1_norms
        summary.scalar("mixture_weight_fractions/{}".format(learner), fraction)

    # The AdaNet-weighted ensemble.
    adanet_weighted_ensemble_spec = self._head.create_estimator_spec(
        features=features,
        mode=mode,
        logits=ensemble_logits,
        labels=labels,
        train_op_fn=lambda _: tf.no_op())

    # A baseline ensemble: the uniform-average of base learner outputs.
    # It is practically free to compute, requiring no additional training, and
    # tends to generalize very well. However the AdaNet-weighted ensemble
    # should perform at least as well given the correct hyperparameters.
    uniform_average_ensemble_logits = tf.add_n([
        wwl.base_learner.logits for wwl in weighted_base_learners
    ]) / len(weighted_base_learners)
    uniform_average_ensemble_spec = self._head.create_estimator_spec(
        features=features,
        mode=mode,
        logits=uniform_average_ensemble_logits,
        labels=labels,
        train_op_fn=lambda _: tf.no_op())

    # The base learner.
    base_learner_spec = self._head.create_estimator_spec(
        features=features,
        mode=mode,
        logits=weighted_base_learners[-1].base_learner.logits,
        labels=labels,
        train_op_fn=lambda _: tf.no_op())

    ensemble_loss = adanet_weighted_ensemble_spec.loss
    adanet_loss = None
    eval_metric_ops = {}
    if mode != tf.estimator.ModeKeys.PREDICT:
      adanet_loss = ensemble_loss + ensemble_complexity_regularization
      eval_metric_ops["loss/adanet/adanet_weighted_ensemble"] = tf.metrics.mean(
          ensemble_loss)
      for metric, ops in adanet_weighted_ensemble_spec.eval_metric_ops.items():
        eval_metric_ops["{}/adanet/adanet_weighted_ensemble".format(
            metric)] = ops
      avg_metric_ops = uniform_average_ensemble_spec.eval_metric_ops
      eval_metric_ops["loss/adanet/uniform_average_ensemble"] = tf.metrics.mean(
          uniform_average_ensemble_spec.loss)
      for metric, ops in avg_metric_ops.items():
        eval_metric_ops["{}/adanet/uniform_average_ensemble".format(
            metric)] = ops
      eval_metric_ops["loss/adanet/base_learner"] = tf.metrics.mean(
          base_learner_spec.loss)
      for metric, ops in base_learner_spec.eval_metric_ops.items():
        eval_metric_ops["{}/adanet/base_learner".format(metric)] = ops

      with tf.name_scope(""):
        summary.scalar("loss/adanet/adanet_weighted_ensemble",
                       adanet_weighted_ensemble_spec.loss)
        summary.scalar("loss/adanet/base_learner", base_learner_spec.loss)
        summary.scalar("loss/adanet/uniform_average_ensemble",
                       uniform_average_ensemble_spec.loss)

    # TODO: Merge AdaNet loss and complexity_regularized_loss.
    complexity_regularized_loss = adanet_loss

    train_op = None
    if mode == tf.estimator.ModeKeys.TRAIN and base_learner_builder:
      with tf.variable_scope("train_base_learner"):
        base_learner_train_op = (
            base_learner_builder.build_base_learner_train_op(
                loss=base_learner_spec.loss,
                var_list=var_list,
                labels=labels,
                summary=summary))
      ensemble_var_list = [w.weight for w in weighted_base_learners]
      if self._use_bias:
        ensemble_var_list.append(bias)
      with tf.variable_scope("train_mixture_weights"):
        ensemble_train_op = base_learner_builder.build_mixture_weights_train_op(
            loss=adanet_loss,
            var_list=ensemble_var_list,
            logits=ensemble_logits,
            labels=labels,
            summary=summary)
      train_op = tf.group(base_learner_train_op, ensemble_train_op)

    return Ensemble(
        name=name,
        weighted_base_learners=weighted_base_learners,
        bias=bias,
        logits=ensemble_logits,
        predictions=adanet_weighted_ensemble_spec.predictions,
        loss=ensemble_loss,
        adanet_loss=adanet_loss,
        complexity_regularized_loss=complexity_regularized_loss,
        train_op=train_op,
        complexity_regularization=ensemble_complexity_regularization,
        eval_metric_ops=eval_metric_ops,
        export_outputs=adanet_weighted_ensemble_spec.export_outputs)

  def _build_weighted_base_learner(self,
                                   base_learner,
                                   logits_dimension,
                                   weight_initializer=None):
    """Builds an `WeightedBaseLearner`.

    Args:
      base_learner: The `BaseLearner` to weight.
      logits_dimension: The number of outputs from the logits.
      weight_initializer: Initializer for the weight variable. Can be a
        `Constant` prior weight to use for warm-starting.

    Returns:
      A `WeightedBaseLearner` instance.
    """

    # Treat base learners as if their weights are frozen, and ensure that
    # mixture weight gradients do not propagate through.
    last_layer = tf.stop_gradient(base_learner.last_layer)

    weight_shape = None
    if weight_initializer is None:
      weight_initializer = tf.zeros_initializer()
      last_layer_size = base_learner.last_layer.get_shape().as_list()[-1]
      weight_shape = [last_layer_size, logits_dimension]

    with tf.variable_scope("logits"):
      weight = tf.get_variable(
          name="mixture_weight",
          shape=weight_shape,
          initializer=weight_initializer)
      logits = tf.matmul(last_layer, weight)
    return WeightedBaseLearner(
        base_learner=base_learner, logits=logits, weight=weight)

  def _create_bias(self, logits_dimension, prior=None):
    """Returns a bias term vector.

    If `use_bias` is set, then it returns a trainable bias variable initialized
    to zero, or warm-started with the given prior. Otherwise it returns
    a zero constant bias.

    Args:
      logits_dimension: The number of outputs from the logits.
      prior: Prior for the bias variable for warm-starting.

    Returns:
      A bias term `Tensor`.
    """

    if not self._use_bias:
      if prior is not None:
        return prior
      return tf.constant(0., name="zero_bias")
    shape = None
    if prior is None:
      prior = tf.zeros_initializer()
      shape = logits_dimension
    return tf.get_variable(name="bias", shape=shape, initializer=prior)