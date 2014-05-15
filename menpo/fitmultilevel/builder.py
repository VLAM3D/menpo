from __future__ import division
import abc
import numpy as np

from menpo.transform import Scale, Translation, GeneralizedProcrustesAnalysis
from menpo.model.pca import PCAModel
from menpo.visualize import print_dynamic, progress_bar_str

from .functions import mean_pointcloud


class DeformableModelBuilder(object):
    r"""
    Abstract class with a set of functions useful to build a Deformable Model.
    """
    __metaclass__ = abc.ABCMeta

    @classmethod
    def check_n_levels(cls, n_levels):
        r"""
        Checks the number of pyramid levels that must be int > 0.
        """
        if not isinstance(n_levels, int) or n_levels < 1:
            raise ValueError("n_levels must be int > 0")

    @classmethod
    def check_downscale(cls, downscale):
        r"""
        Checks the downscale factor of the pyramid that must be >= 1.
        """
        if downscale < 1:
            raise ValueError("downscale must be >= 1")

    @classmethod
    def check_normalization_diagonal(cls, normalization_diagonal):
        r"""
        Checks the diagonal length used to normalize the images' size that
        must be >= 20.
        """
        if normalization_diagonal is not None and normalization_diagonal < 20:
            raise ValueError("normalization_diagonal must be >= 20")

    @classmethod
    def check_boundary(cls, boundary):
        r"""
        Checks the boundary added around the reference shape that must be
        int >= 0.
        """
        if not isinstance(boundary, int) or boundary < 0:
            raise ValueError("boundary must be >= 0")

    @classmethod
    def check_max_components(cls, max_components, n_levels, var_name):
        r"""
        Checks the maximum number of components per level either of the shape
        or the appearance model. It must be None or int or float or a list of
        those containing 1 or {n_levels} elements.
        """
        str_error = ("{} must be None or an int > 0 or a 0 <= float <= 1 or "
                     "a list of those containing 1 or {} elements").format(
                         var_name, n_levels)
        if not isinstance(max_components, list):
            max_components_list = [max_components] * n_levels
        elif len(max_components) is 1:
            max_components_list = [max_components[0]] * n_levels
        elif len(max_components) is n_levels:
            max_components_list = max_components
        else:
            raise ValueError(str_error)
        for comp in max_components_list:
            if comp is not None:
                if not isinstance(comp, int):
                    if not isinstance(comp, float):
                        raise ValueError(str_error)
        return max_components_list

    @classmethod
    def check_feature_type(cls, feature_type, n_levels, pyramid_on_features):
        r"""
        Checks the feature type per level.
        If pyramid_on_features is False, it must be a string or a
        function/closure or a list of those containing 1 or {n_levels}
        elements.
        If pyramid_on_features is True, it must be a string or a
        function/closure or a list of 1 of those.
        """
        if pyramid_on_features is False:
            feature_type_str_error = ("feature_type must be a str or a "
                                      "function/closure or a list of "
                                      "those containing 1 or {} "
                                      "elements").format(n_levels)
            if not isinstance(feature_type, list):
                feature_type_list = [feature_type] * n_levels
            elif len(feature_type) is 1:
                feature_type_list = [feature_type[0]] * n_levels
            elif len(feature_type) is n_levels:
                feature_type_list = feature_type
            else:
                raise ValueError(feature_type_str_error)
        else:
            feature_type_str_error = ("pyramid_on_features is enabled so "
                                      "feature_type must be a str or a "
                                      "function/closure or a list "
                                      "containing 1 of those")
            if not isinstance(feature_type, list):
                feature_type_list = [feature_type]
            elif len(feature_type) is 1:
                feature_type_list = feature_type
            else:
                raise ValueError(feature_type_str_error)
        for ft in feature_type_list:
            if ft is not None:
                if not isinstance(ft, str):
                    if not hasattr(ft, '__call__'):
                        raise ValueError(feature_type_str_error)
        return feature_type_list

    @abc.abstractmethod
    def build(self, images, group=None, label='all'):
        r"""
        Builds a Multilevel Deformable Model.
        """
        pass

    @classmethod
    def _normalization_wrt_reference_shape(cls, images, group, label,
                                           normalization_diagonal,
                                           interpolator, verbose=False):
        r"""
        Function that normalizes the images sizes with respect to the reference
        shape (mean shape) scaling. This step is essential before building a
        deformable model.

        The normalization includes:
        1) Computation of the reference shape as the mean shape of the images'
           landmarks.
        2) Scaling of the reference shape using the normalization_diagonal.
        3) Rescaling of all the images so that their shape's scale is in
           correspondence with the reference shape's scale.

        Parameters
        ----------
        images: list of :class:`menpo.image.Image`
            The set of landmarked images from which to build the AAM.
        group : string
            The key of the landmark set that should be used. If None,
            and if there is only one set of landmarks, this set will be used.
        label: string
            The label of of the landmark manager that you wish to use. If no
            label is passed, the convex hull of all landmarks is used.
        normalization_diagonal: int
            During building an AAM, all images are rescaled to ensure that the
            scale of their landmarks matches the scale of the mean shape.

            If int, it ensures that the mean shape is scaled so that the
            diagonal of the bounding box containing it matches the
            normalization_diagonal value.
            If None, the mean shape is not rescaled.

            Note that, because the reference frame is computed from the mean
            landmarks, this kwarg also specifies the diagonal length of the
            reference frame (provided that features computation does not change
            the image size).
        interpolator: string
            The interpolator that should be used to perform the warps.
        verbose: bool, Optional
            Flag that controls information and progress printing.

            Default: False

        Returns
        -------
        reference_shape: Pointcloud
            The reference shape that was used to resize all training images to
            a consistent object size.
        """
        # the reference_shape is the mean shape of the images' landmarks
        if verbose:
            print_dynamic('- Computing reference shape')
        shapes = [i.landmarks[group][label].lms for i in images]
        reference_shape = mean_pointcloud(shapes)

        # fix the reference_shape's diagonal length if asked
        if normalization_diagonal:
            x, y = reference_shape.range()
            scale = normalization_diagonal / np.sqrt(x**2 + y**2)
            Scale(scale, reference_shape.n_dims).apply_inplace(reference_shape)

        # normalize the scaling of all images wrt the reference_shape size
        normalized_images = []
        for c, i in enumerate(images):
            if verbose:
                print_dynamic('- Normalizing images size - {}'.format(
                    progress_bar_str((c + 1.) / len(images),
                                     show_bar=False)))
            normalized_images.append(i.rescale_to_reference_shape(
                reference_shape, group=group, label=label,
                interpolator=interpolator))

        if verbose:
            print_dynamic('- Normalizing images size - Done\n')

        return reference_shape

    @classmethod
    def _preprocessing(cls, images, group, label, normalization_diagonal,
                       interpolator, scaled_shape_models, n_levels, downscale,
                       verbose=False):
        r"""
        Function that applies some preprocessing steps on a set of images.
        These steps are essential before building a deformable model.

        The preprocessing includes:
        1) Computation of the reference shape as the mean shape of the images'
           landmarks.
        2) Scaling of the reference shape using the normalization_diagonal.
        3) Rescaling of all the images so that their shape's scale is in
           correspondence with the reference shape's scale.
        4) Creation of the generator function for a smoothing or Gaussian
           pyramid.

        Parameters
        ----------
        images: list of :class:`menpo.image.Image`
            The set of landmarked images from which to build the AAM.
        group : string
            The key of the landmark set that should be used. If None,
            and if there is only one set of landmarks, this set will be used.
        label: string
            The label of of the landmark manager that you wish to use. If no
            label is passed, the convex hull of all landmarks is used.
        normalization_diagonal: int
            During building an AAM, all images are rescaled to ensure that the
            scale of their landmarks matches the scale of the mean shape.

            If int, it ensures that the mean shape is scaled so that the
            diagonal of the bounding box containing it matches the
            normalization_diagonal value.
            If None, the mean shape is not rescaled.

            Note that, because the reference frame is computed from the mean
            landmarks, this kwarg also specifies the diagonal length of the
            reference frame (provided that features computation does not change
            the image size).
        interpolator: string
            The interpolator that should be used to perform the warps.
        scaled_shape_models: boolean
            If True, the original images will be smoothed with a smoothing
            pyramid and the shape models (reference frames) will be scaled with
            a Gaussian pyramid.
            If False, the original images will be scaled with a Gaussian
            pyramid and the shape models (reference frames) will have the same
            scale (the one of the highest pyramidal level).
        n_levels: int
            The number of multi-resolution pyramidal levels to be used.
        downscale: float
            The downscale factor that will be used to create the different
            pyramidal levels.
        verbose: bool, Optional
            Flag that controls information and progress printing.

            Default: False

        Returns
        -------
        reference_shape: Pointcloud
            The reference shape that was used to resize all training images to a
            consistent object size.
        generator: function
            The generator function of the smoothing or Gaussian pyramid.
        """
        if verbose:
            intro_str = '- Preprocessing: '

        # the mean shape of the images' landmarks is the reference_shape
        if verbose:
            print_dynamic('{}Computing reference shape'.format(intro_str))
        shapes = [i.landmarks[group][label].lms for i in images]
        reference_shape = mean_pointcloud(shapes)

        # fix the reference_shape's diagonal length if asked
        if normalization_diagonal:
            x, y = reference_shape.range()
            scale = normalization_diagonal / np.sqrt(x**2 + y**2)
            Scale(scale, reference_shape.n_dims).apply_inplace(reference_shape)

        # normalize the scaling of all shapes wrt the reference_shape
        normalized_images = []
        for c, i in enumerate(images):
            if verbose:
                print_dynamic('{}Normalizing object size - {}'.format(
                    intro_str, progress_bar_str(float(c + 1) / len(images),
                                                show_bar=False)))
            normalized_images.append(i.rescale_to_reference_shape(
                reference_shape, group=group, label=label,
                interpolator=interpolator))

        # generate pyramid
        if verbose:
            print_dynamic('{}Generating multilevel scale space'.format(
                intro_str))
        if scaled_shape_models:
            generator = [i.smoothing_pyramid(n_levels=n_levels,
                                             downscale=downscale)
                         for i in normalized_images]
        else:
            generator = [i.gaussian_pyramid(n_levels=n_levels,
                                            downscale=downscale)
                         for i in normalized_images]

        if verbose:
            print_dynamic('{}Done\n'.format(intro_str))

        return reference_shape, generator

    #TODO: this seems useful on its own, maybe it shouldn't be underscored...
    @classmethod
    def _build_shape_model(cls, shapes, max_components):
        r"""
        Builds a shape model given a set of shapes.

        Parameters
        ----------
        shapes: list of :class:`Pointcloud`
            The set of shapes from which to build the model.
        max_components: None or int or float
            Specifies the number of components of the trained shape model.
            If int, it specifies the exact number of components to be retained.
            If float, it specifies the percentage of variance to be retained.
            If None, all the available components are kept (100% of variance).

        Returns
        -------
        shape_model: :class:`menpo.model.pca`
            The PCA shape model.
        """
        # centralize shapes
        centered_shapes = [Translation(-s.centre).apply(s) for s in shapes]
        # align centralized shape using Procrustes Analysis
        gpa = GeneralizedProcrustesAnalysis(centered_shapes)
        aligned_shapes = [s.aligned_source for s in gpa.transforms]

        # build shape model
        shape_model = PCAModel(aligned_shapes)
        if max_components is not None:
            # trim shape model if required
            shape_model.trim_components(max_components)

        return shape_model
