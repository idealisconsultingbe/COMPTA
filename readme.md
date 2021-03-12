# appserver-template 14.0
This repository is configured to build an Odoo 14 appserver using buildout and the anybox.recipe.odoo.

## DOCKER
### Migrate to docker
You can use the script **"migrate_to_docker.sh"** to convert an appserver to docker.

Copy the script into an appserver, then run the command:
```
./migrate_to_docker.sh
```

In the new format, the directories are moved to:
- local_addons => src
- parts => vendor
- py36 => venv
- .buildout: all folders and files used by buildout  

### Ubuntu (TODO)
./docker_build.sh <template_name> (ex: ./docker_build.sh idealis:14.0)

### Windows (TODO)
With PyCharm: Edit docker-compose-build.yml, and change:
- SSH_KEY: copy your private ssh key in this arg
- image: set to image name (ex: idealis:14.0)

## BUILDOUT
Please only update **[odoo]** part.

### Version
This will select which version of Odoo to use.
Update the last part of version line to select the Odoo branch to pull.
In Example below, the version is 14.0
```
version = git http://github.com/odoo/odoo.git odoo 14.0
```

### Addons
Allow to add custom addons by setting the repository where to fetch them.
One line per repository
The line is composed in multiple parts to set, used to fetch into a directory

- It starts with the kind of repository to use:
     * `local`: local folder
     * `git`: Git repository
     * `bzr`: Bazaar repository
     * ...
- Then, set:
     * the folder if type is local
     * the repository, otherwise
- Next (except for local type), set the folder where the repository will be stored
- Finally (except for local type), write the name of the branch to fetch

Example:
```
git https://github.com/OCA/server-tools.git parts/community/addons-oca-server-tools 14.0
```

### Eggs
Here a set the python libraries to install.
Just add a new line per lib

### Pre-commit
To install the pre-commit hook, go to the workspace directory, and execute following commands
```
pip install pre-commit
pre-commit install
```

### Docker
Build an image with
```
./docker_build.sh registry.myidealis.be/<GROUP>/<REPO>:<TAG_INCREMENT>
docker push registry.myidealis.be/<GROUP>/<REPO>:<TAG_INCREMENT>
```

Image shoud be visible in registry (in gitlab) at the end of the operation.

Deploy by changing tag in manage.sh on production server, then re-deploy.

## LICENCE
Files in this repository are Licensed under the LGPL and A-GPL Licence.
 

