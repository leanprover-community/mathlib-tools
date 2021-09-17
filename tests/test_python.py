""" Tests API provided by `mathlibtools` to other Python scripts """
import mathlibtools


def test_version():
	assert isinstance(mathlibtools.__version__, str)
