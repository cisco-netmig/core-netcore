from setuptools import setup, find_packages

# Read the README file to include in the long description
with open('README.md', encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='netcore',
    version='1.0.0',  # You can dynamically generate this if needed
    author='Sanjeev Krishna',
    author_email='sanjeekr@cisco.com',
    description='A toolkit for network automation including terminal access, parsing, and Excel export.',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://wwwin-github.cisco.com/sanjeekr/netcore',
    packages=find_packages(include=['netcore', 'netcore.*']),
    include_package_data=True,
    package_data={
        'netcore': [
            'ntc_templates/*',
        ],
    },
    install_requires=[
        'netmiko>=4.0.0',
        'paramiko>=2.9.2',
        'textfsm',
        'ntc_templates>=7.4.0',
        'xlsxwriter',
        'xlrd>=2.0.1'
    ],
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Development Status :: 4 - Beta',
        'Intended Audience :: Network Automation Engineers',
        'Topic :: System :: Networking',
    ],
    python_requires='>=3.10',
)
