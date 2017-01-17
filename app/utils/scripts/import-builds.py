#!/usr/bin/python
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Get build data from production and import into local DB."""

import argparse
import bson
import datetime
import json
import requests
from urlparse import urljoin

import models
import models.build as mbuild
import utils
import utils.db
import utils.build

BACKEND_URL = "https://api.kernelci.org"

def import_build(job, kernel, build):
    build_dir = None
    defconfig = build[models.DEFCONFIG_KEY]
    kconfig_fragments = build.get(models.KCONFIG_FRAGMENTS_KEY, None)
    defconfig_full = build[models.DEFCONFIG_FULL_KEY]

    defconfig_full = utils.get_defconfig_full(build_dir, defconfig, defconfig_full, kconfig_fragments)

    build_doc = mbuild.BuildDocument(job, kernel, defconfig, defconfig_full=defconfig_full)

    build_doc.dirname = build_dir
    build_doc.arch = build.get(models.ARCHITECTURE_KEY, None)
    build_doc.build_log = build.get(models.BUILD_LOG_KEY, None)
    build_doc.build_platform = build.get(models.BUILD_PLATFORM_KEY, [])
    build_doc.build_time = build.get(models.BUILD_TIME_KEY, 0)
    build_doc.build_type = build.get(models.BUILD_TYPE_KEY, models.KERNEL_BUILD_TYPE)
    build_doc.dtb_dir = build.get(models.DTB_DIR_KEY, None)
    build_doc.errors = build.get(models.BUILD_ERRORS_KEY, 0)
    build_doc.file_server_resource = build.get(models.FILE_SERVER_RESOURCE_KEY, None)
    build_doc.file_server_url = build.get(models.FILE_SERVER_URL_KEY, None)
    build_doc.git_branch = build.get(models.GIT_BRANCH_KEY, None)
    build_doc.git_commit = build.get(models.GIT_COMMIT_KEY, None)
    build_doc.git_describe = build.get(models.GIT_DESCRIBE_KEY, None)
    build_doc.git_url = build.get(models.GIT_URL_KEY, None)
    build_doc.kconfig_fragments = kconfig_fragments
    build_doc.kernel_config = build.get(models.KERNEL_CONFIG_KEY, None)
    build_doc.kernel_image = build.get(models.KERNEL_IMAGE_KEY, None)
    build_doc.modules = build.get(models.MODULES_KEY, None)
    build_doc.modules_dir = build.get(models.MODULES_DIR_KEY, None)
    build_doc.status = build.get(models.BUILD_RESULT_KEY, models.UNKNOWN_STATUS)
    build_doc.system_map = build.get(models.SYSTEM_MAP_KEY, None)
    build_doc.text_offset = build.get(models.TEXT_OFFSET_KEY, None)
    build_doc.version = build.get(models.VERSION_KEY, "1.0")
    build_doc.warnings = build.get(models.BUILD_WARNINGS_KEY, 0)
    build_doc.kernel_image_size = build.get(models.KERNEL_IMAGE_SIZE_KEY, None)
    build_doc.modules_size = build.get(models.MODULES_SIZE_KEY, None)
    build_doc.cross_compile = build.get(models.CROSS_COMPILE_KEY, None)

    build_doc.git_describe_v = build.get(models.GIT_DESCRIBE_V_KEY, None)
    build_doc.kernel_version = utils.build._extract_kernel_version(
        build_doc.git_describe_v, build_doc.git_describe)

    compiler_version_full = (
        build.get(models.COMPILER_VERSION_FULL_KEY, None) or
        build.get(models.COMPILER_VERSION_KEY, None))

    compiler_data = utils.build._extract_compiler_data(compiler_version_full)
    build_doc.compiler = compiler_data[0]
    build_doc.compiler_version = compiler_data[1]
    build_doc.compiler_version_ext = compiler_data[2]
    build_doc.compiler_version_full = compiler_data[3]

    build_doc.created_on = datetime.datetime.now(tz=bson.tz_util.utc)

    database = utils.db.get_db_connection({})
    ret_val, build_id = utils.db.save(database, build_doc, manipulate=True)

    print "Imported build with id %s" % build_id

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", help="authorization token for the REST API", required=True)
    parser.add_argument("--job", help="name of tree (eg. mainline)", default="mainline")
    parser.add_argument("--kernel", help="version of the sources (eg. v4.9)", default="v4.9")
    args = parser.parse_args()

    params = dict()
    params["job"] = args.job
    params["kernel"] = args.kernel

    headers = dict()
    headers["Authorization"] = args.token
    
    url = urljoin(BACKEND_URL, "/build")
    response = requests.get(url, params=params, headers=headers)
    json_obj = json.loads(response.content.decode("utf8"))

    for build in json_obj["result"]:
    	import_build(args.job, args.kernel, build)

