import setuptools


AUTHORS = [
    'Arne Traue', 'Gerrit Book', 'Praneeth Balakrishna',
    'Pascal Peters', 'Pramod Manjunatha', 'Darius Jakobeit',
    'Max Schenke', 'Wilhelm Kirchgässner', 'Oliver Wallscheid',
]

with open('requirements.txt', 'r') as f:
    requirements = f.read().splitlines()

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
      name='gym_electric_motor',
      version='0.3.0',
      description='An OpenAI gym environment for electric motor control.',
      packages=setuptools.find_packages(),
      install_requires=requirements,
      python_requires='>=3.6',
      extras_require={'examples': [
                        'keras-rl2 @git+https://github.com/wau/keras-rl2.git',
                        'stable-baselines3',
                        'tensorforce==0.5.5']
                     },
      author=', '.join(sorted(AUTHORS, key=lambda n: n.split()[-1].lower())),
      long_description=long_description,
      long_description_content_type="text/markdown",
      url="https://github.com/upb-lea/gym-electric-motor",
      )
