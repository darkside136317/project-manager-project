from setuptools import find_packages, setup

with open("requirements.txt") as f:
    install_requires = [
        line.strip() for line in f.read().strip().split("\n")
        if line.strip() and not line.startswith("#") and not line.startswith("frappe")
    ]

setup(
    name="pm_archive",
    version="0.1.0",
    description="Quản lý dự án — lưu trữ hồ sơ dự án",
    author="Project Manager Team",
    author_email="admin@pm.localhost",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
)
