import torch

from ..models import AutoEncodingDiscriminator
from .functional import (
    energy_based_discriminator_loss,
    energy_based_generator_loss,
    energy_based_pulling_away_term,
)
from .loss import DiscriminatorLoss, GeneratorLoss

__all__ = [
    "EnergyBasedGeneratorLoss",
    "EnergyBasedDiscriminatorLoss",
    "EnergyBasedPullingAwayTerm",
]


class EnergyBasedGeneratorLoss(GeneratorLoss):
    r"""Energy Based GAN generator loss from `"Energy Based Generative Adversarial Network
    by Zhao et. al." <https://arxiv.org/abs/1609.03126>`_ paper.

    The loss can be described as:

    .. math:: L(G) = D(G(z))

    where

    - :math:`G` : Generator
    - :math:`D` : Discriminator
    - :math:`z` : A sample from the noise prior

    Args:
        reduction (str, optional): Specifies the reduction to apply to the output.
            If ``none`` no reduction will be applied. If ``mean`` the outputs are averaged over batch size.
            If ``sum`` the elements of the output are summed.
        override_train_ops (function, optional): A function is passed to this argument,
            if the default ``train_ops`` is not to be used.
    """

    def forward(self, dgz):
        r"""Computes the loss for the given input.

        Args:
            dgz (torch.Tensor): Output of the Discriminator with generated data. It must have the
                                dimensions (N, \*) where \* means any number of additional
                                dimensions.

        Returns:
            scalar if reduction is applied else Tensor with dimensions (N, \*).
        """
        return energy_based_generator_loss(dgz, self.reduction)

    def train_ops(
        self,
        generator,
        discriminator,
        optimizer_generator,
        device,
        batch_size,
        labels=None,
    ):
        r"""This function sets the ``embeddings`` attribute of the ``AutoEncodingDiscriminator`` to
        ``False`` and calls the ``train_ops`` of the ``GeneratorLoss``. After the call the
        attribute is again set to ``True``.

        Args:
            generator (torchgan.models.Generator): The model to be optimized.
            discriminator (torchgan.models.Discriminator): The discriminator which judges the
                performance of the generator.
            optimizer_generator (torch.optim.Optimizer): Optimizer which updates the ``parameters``
                of the ``generator``.
            device (torch.device): Device on which the ``generator`` and ``discriminator`` is present.
            batch_size (int): Batch Size of the data infered from the ``DataLoader`` by the ``Trainer``.
            labels (torch.Tensor, optional): Labels for the data.

        Returns:
            Scalar value of the loss.
        """
        if self.override_train_ops is not None:
            return self.override_train_ops(
                generator,
                discriminator,
                optimizer_generator,
                device,
                batch_size,
                labels,
            )
        else:
            if isinstance(discriminator, AutoEncodingDiscriminator):
                orig_value = getattr(discriminator, "embeddings")
                setattr(discriminator, "embeddings", False)
            loss = super(EnergyBasedGeneratorLoss, self).train_ops(
                generator,
                discriminator,
                optimizer_generator,
                device,
                batch_size,
                labels,
            )
            if isinstance(discriminator, AutoEncodingDiscriminator):
                setattr(discriminator, "embeddings", orig_value)
            return loss


class EnergyBasedPullingAwayTerm(GeneratorLoss):
    r"""Energy Based Pulling Away Term from `"Energy Based Generative Adversarial Network
    by Zhao et. al." <https://arxiv.org/abs/1609.03126>`_ paper.

    The loss can be described as:

    .. math:: f_{PT}(S) = \frac{1}{N(N-1)}\sum_i\sum_{j \neq i}\bigg(\frac{S_i^T S_j}{||S_i||\ ||S_j||}\bigg)^2

    where

    - :math:`S` : The feature output from the encoder for generated images
    - :math:`N` : Batch Size of the Input

    Args:
        pt_ratio (float, optional): The weight given to the pulling away term.
        override_train_ops (function, optional): A function is passed to this argument,
            if the default ``train_ops`` is not to be used.
    """

    def __init__(self, pt_ratio=0.1, override_train_ops=None):
        super(EnergyBasedPullingAwayTerm, self).__init__(
            "mean", override_train_ops
        )
        self.pt_ratio = pt_ratio

    def forward(self, dgz, d_hid):
        r"""Computes the loss for the given input.

        Args:
            dgz (torch.Tensor) : Output of the Discriminator with generated data. It must have the
                                 dimensions (N, \*) where \* means any number of additional
                                 dimensions.
            d_hid (torch.Tensor): The embeddings generated by the discriminator.

        Returns:
            scalar.
        """
        return self.pt_ratio * energy_based_pulling_away_term(d_hid)

    def train_ops(
        self,
        generator,
        discriminator,
        optimizer_generator,
        device,
        batch_size,
        labels=None,
    ):
        r"""This function extracts the hidden embeddings of the discriminator network. The furthur
        computation is same as the standard train_ops.

        .. note::
            For the loss to work properly, the discriminator must be a ``AutoEncodingDiscriminator``
            and it must have a ``embeddings`` attribute which should be set to ``True``. Also the
            generator ``label_type`` must be ``none``. As a result of these constraints it advisable
            not to use custom models with this loss. This will be improved in future.

        Args:
            generator (torchgan.models.Generator): The model to be optimized.
            discriminator (torchgan.models.Discriminator): The discriminator which judges the
                performance of the generator.
            optimizer_generator (torch.optim.Optimizer): Optimizer which updates the ``parameters``
                of the ``generator``.
            device (torch.device): Device on which the ``generator`` and ``discriminator`` is present.
            batch_size (int): Batch Size of the data infered from the ``DataLoader`` by the ``Trainer``.
            labels (torch.Tensor, optional): Labels for the data.

        Returns:
            Scalar value of the loss.
        """
        if self.override_train_ops is not None:
            return self.override_train_ops(
                generator,
                discriminator,
                optimizer_generator,
                device,
                batch_size,
                labels,
            )
        else:
            if not isinstance(discriminator, AutoEncodingDiscriminator):
                raise Exception(
                    "EBGAN PT requires the Discriminator to be a AutoEncoder"
                )
            if not generator.label_type == "none":
                raise Exception(
                    "EBGAN PT supports models which donot require labels"
                )
            if not discriminator.embeddings:
                raise Exception(
                    "EBGAN PT requires the embeddings for loss computation"
                )
            noise = torch.randn(
                batch_size, generator.encoding_dims, device=device
            )
            optimizer_generator.zero_grad()
            fake = generator(noise)
            d_hid, dgz = discriminator(fake)
            loss = self.forward(dgz, d_hid)
            loss.backward()
            optimizer_generator.step()
            return loss.item()


class EnergyBasedDiscriminatorLoss(DiscriminatorLoss):
    r"""Energy Based GAN generator loss from `"Energy Based Generative Adversarial Network
    by Zhao et. al." <https://arxiv.org/abs/1609.03126>`_ paper

    The loss can be described as:

    .. math:: L(D) = D(x) + max(0, m - D(G(z)))

    where

    - :math:`G` : Generator
    - :math:`D` : Discriminator
    - :math:`m` : Margin Hyperparameter
    - :math:`z` : A sample from the noise prior

    .. note::
        The convergence of EBGAN is highly sensitive to hyperparameters. The ``margin``
        hyperparameter as per the paper was taken as follows:

        +----------------------+--------+
        | Dataset              | Margin |
        +======================+========+
        | MNIST                | 10.0   |
        +----------------------+--------+
        | LSUN                 | 80.0   |
        +----------------------+--------+
        | CELEB A              | 20.0   |
        +----------------------+--------+
        | Imagenet (128 x 128) | 40.0   |
        +----------------------+--------+
        | Imagenet (256 x 256) | 80.0   |
        +----------------------+--------+

    Args:
        reduction (str, optional): Specifies the reduction to apply to the output.
            If ``none`` no reduction will be applied. If ``mean`` the outputs are averaged over batch size.
            If ``sum`` the elements of the output are summed.
        margin (float, optional): The margin hyperparameter.
        override_train_ops (function, optional): Function to be used in place of the default ``train_ops``
    """

    def __init__(self, reduction="mean", margin=80.0, override_train_ops=None):
        super(EnergyBasedDiscriminatorLoss, self).__init__(
            reduction, override_train_ops
        )
        self.margin = margin

    def forward(self, dx, dgz):
        r"""Computes the loss for the given input.

        Args:
            dx (torch.Tensor): Output of the Discriminator with real data. It must have the
                               dimensions (N, \*) where \* means any number of additional
                               dimensions.
            dgz (torch.Tensor): Output of the Discriminator with generated data. It must have the
                                dimensions (N, \*) where \* means any number of additional
                                dimensions.

        Returns:
            scalar if reduction is applied else Tensor with dimensions (N, \*).
        """
        return energy_based_discriminator_loss(
            dx, dgz, self.margin, self.reduction
        )

    def train_ops(
        self,
        generator,
        discriminator,
        optimizer_discriminator,
        real_inputs,
        device,
        batch_size,
        labels=None,
    ):
        r"""This function sets the ``embeddings`` attribute of the ``AutoEncodingDiscriminator`` to
        ``False`` and calls the ``train_ops`` of the ``DiscriminatorLoss``. After the call the
        attribute is again set to ``True``.

        Args:
            generator (torchgan.models.Generator): The model to be optimized.
            discriminator (torchgan.models.Discriminator): The discriminator which judges the
                performance of the generator.
            optimizer_discriminator (torch.optim.Optimizer): Optimizer which updates the ``parameters``
                of the ``discriminator``.
            real_inputs (torch.Tensor): The real data to be fed to the ``discriminator``.
            device (torch.device): Device on which the ``generator`` and ``discriminator`` is present.
            batch_size (int): Batch Size of the data infered from the ``DataLoader`` by the ``Trainer``.
            labels (torch.Tensor, optional): Labels for the data.

        Returns:
            Scalar value of the loss.
        """
        if self.override_train_ops is not None:
            return self.override_train_ops(
                self,
                generator,
                discriminator,
                optimizer_discriminator,
                real_inputs,
                device,
                labels,
            )
        else:
            if isinstance(discriminator, AutoEncodingDiscriminator):
                orig_value = getattr(discriminator, "embeddings")
                setattr(discriminator, "embeddings", False)
            loss = super(EnergyBasedDiscriminatorLoss, self).train_ops(
                generator,
                discriminator,
                optimizer_discriminator,
                real_inputs,
                device,
                labels,
            )
            if isinstance(discriminator, AutoEncodingDiscriminator):
                setattr(discriminator, "embeddings", orig_value)
            return loss
