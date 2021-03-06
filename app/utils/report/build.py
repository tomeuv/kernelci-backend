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

"""Create the build email report."""

import pymongo

import models
import utils.db
import utils.report.common as rcommon

# Register normal Unicode gettext.
G_ = rcommon.L10N.ugettext
# Register plural forms Unicode gettext.
P_ = rcommon.L10N.ungettext

# pylint: disable=star-args

BUILD_SEARCH_FIELDS = [
    models.ARCHITECTURE_KEY,
    models.DEFCONFIG_FULL_KEY,
    models.ERRORS_KEY,
    models.ID_KEY,
    models.STATUS_KEY,
    models.WARNINGS_KEY
]

BUILD_SEARCH_SORT = [
    (models.DEFCONFIG_KEY, pymongo.ASCENDING),
    (models.DEFCONFIG_FULL_KEY, pymongo.ASCENDING),
    (models.ARCHITECTURE_KEY, pymongo.ASCENDING)
]

# Various build URLS.
DEFCONFIG_URL = (
    u"{build_url:s}/{job:s}/branch/{git_branch:s}/kernel/{kernel:s}"
    u"/defconfig/{defconfig:s}/")
DEFCONFIG_ID_URL = (u"{build_url:s}/id/{build_id:s}/")
LOG_URL = (
    u"{storage_url:s}/{job:s}/{git_branch:}/{kernel:s}/{arch:s}" +
    u"/{defconfig:s}/" + utils.BUILD_LOG_FILE)
ERR_LOG_URL = (
    u"{storage_url:s}/{job:s}/{git_branch:s}/{kernel:s}/{arch:s}" +
    u"/{defconfig:s}/" + utils.BUILD_ERRORS_FILE)
WARN_LOG_URL = (
    u"{storage_url:s}/{job:s}/{git_branch:s}/{kernel:s}/{arch:s}" +
    u"/{defconfig:s}/" + utils.BUILD_WARNINGS_FILE)
MISM_LOG_URL = (
    u"{storage_url:s}/{job:s}/{git_branch:s}/{kernel:s}/{arch:s}" +
    u"/{defconfig:s}/" + utils.BUILD_MISMATCHES_FILE)
BUILD_SUMMARY_URL = \
    u"{build_url:s}/{job:s}/branch/{git_branch:}/kernel/{kernel:s}/"


# Other template strings.
DEFCONFIG_URL_HTML = u"<a href=\"{defconfig_url:s}\">{defconfig:s}</a>"
STATUS_HTML = (
    u"<a style=\"color: {red:s}\" href=\"{log_url:s}\">{status:s}</a>"
)
ERR_STR_HTML = (
    u"<a style=\"color: {red:s};\" href=\"{err_log_url:s}\">"
    u"{err_string:s}</a>"
)
WARN_STR_HTML = (
    u"<a style=\"color: {yellow:s};\" href=\"{warn_log_url:s}\">"
    u"{warn_string:s}</a>"
)


def _get_errors_count(results):
    """Parse the build data and get errors and warnings.

    :param results: The results to parse.
    :type results: pymongo.cursor.Cursor.
    :return The errors data structure, the errors and warnings count and the
    build id value.
    """
    err_data = {}
    total_errors = total_warnings = 0

    arch_keys = err_data.viewkeys()

    for result in results:
        res_get = result.get

        arch = res_get(models.ARCHITECTURE_KEY)
        defconfig = res_get(models.DEFCONFIG_KEY)
        defconfig_full = res_get(models.DEFCONFIG_FULL_KEY, defconfig)
        res_errors = res_get(models.ERRORS_KEY, 0)
        res_warnings = res_get(models.WARNINGS_KEY, 0)

        if defconfig_full is None:
            defconfig_full = defconfig

        err_struct = {}

        if res_errors is not None and res_errors != 0:
            total_errors += res_errors
            err_struct[models.ERRORS_KEY] = res_errors

        if res_warnings is not None and res_warnings != 0:
            total_warnings += res_warnings
            err_struct[models.WARNINGS_KEY] = res_warnings

        if err_struct:
            err_struct[models.BUILD_ID_KEY] = res_get(models.ID_KEY)

            if arch in arch_keys:
                if defconfig_full in err_data[arch].keys():
                    # Multiple builds with the same defconfig value?
                    err_data[arch][defconfig_full][models.WARNINGS_KEY] += \
                        res_warnings
                    err_data[arch][defconfig_full][models.ERRORS_KEY] += \
                        res_errors
                else:
                    err_data[arch][defconfig_full] = err_struct
            else:
                err_data[arch] = {}
                err_data[arch][defconfig_full] = err_struct

    return err_data, total_errors, total_warnings


def _parse_build_data(results):
    """Parse the build data to provide a writable data structure.

    Loop through the build data found, and create a new dictionary whose keys
    are the architectures and their values a list of tuples of
    (defconfig, status, build_id).

    :param results: The results to parse.
    :type results: pymongo.cursor.Cursor.
    :return A dictionary.
    """
    parsed_data = {}
    arch_keys = parsed_data.viewkeys()

    for result in results:
        res_get = result.get

        arch = res_get(models.ARCHITECTURE_KEY)
        defconfig = res_get(models.DEFCONFIG_FULL_KEY, None) or \
            res_get(models.DEFCONFIG_KEY)

        struct = (
            defconfig,
            res_get(models.STATUS_KEY),
            res_get(models.ID_KEY)
        )

        if arch in arch_keys:
            parsed_data[arch].append(struct)
        else:
            parsed_data[arch] = []
            parsed_data[arch].append(struct)

    return parsed_data


# pylint: disable=too-many-locals
def _get_build_subject_string(**kwargs):
    """Create the build email subject line.

    This is used to created the custom email report line based on the number
    of values we have.

    :param total_count: The total number of build reports.
    :type total_count: integer
    :param fail_count: The number of failed build reports.
    :type fail_count: integer
    :param pass_count: The number of successful build reports.
    :type pass_count: integer
    :param job: The name of the job.
    :type job: string
    :param kernel: The name of the kernel.
    :type kernel: string
    :return The subject string.
    """
    k_get = kwargs.get
    total_count = k_get("total_count", 0)
    errors = k_get("errors_count", 0)
    warnings = k_get("warnings_count", 0)

    subject_str = u""

    base_subject = G_(u"{job:s}/{git_branch:s} build")
    kernel_name = G_(u"({kernel:s})")
    failed_builds = G_(u"{fail_count:d} failed")
    passed_builds = G_(u"{pass_count:d} passed")
    total_builds = P_(
        u"{total_count:d} build", u"{total_count:d} builds", total_count)
    errors_string = P_(
        u"{errors_count:d} error", u"{errors_count:d} errors", errors)
    warnings_string = P_(
        u"{warnings_count:d} warning",
        u"{warnings_count:d} warnings", warnings)

    # Base format string to create the subject line.
    # 1st, 2nd, 3rd, 4th: job name, total count, fail count, pass count.
    # The last one is always the kernel/git-describe name.
    # The others will contain errors and warnings count.
    # next build: 0 failed, 10 passed (next-20150401)
    base_0 = G_(u"{:s}: {:s}: {:s}, {:s} {:s}")
    # next build: 0 failed, 10 passed, 2 warnings (next-20150401)
    base_1 = G_(u"{:s}: {:s}: {:s}, {:s}, {:s} {:s}")
    # next build: 0 failed, 10 passed, 1 error, 2 warnings (next-20150401)
    base_2 = G_(u"{:s}: {:s}: {:s}, {:s}, {:s}, {:s} {:s}")

    if errors == 0 and warnings == 0:
        subject_str = base_0.format(
            base_subject,
            total_builds, failed_builds, passed_builds, kernel_name)
    elif errors == 0 and warnings != 0:
        subject_str = base_1.format(
            base_subject,
            total_builds,
            failed_builds, passed_builds, warnings_string, kernel_name)
    elif errors != 0 and warnings != 0:
        subject_str = base_2.format(
            base_subject,
            total_builds,
            failed_builds,
            passed_builds, errors_string, warnings_string, kernel_name)
    elif errors != 0 and warnings == 0:
        subject_str = base_1.format(
            base_subject,
            total_builds,
            failed_builds, passed_builds, errors_string, kernel_name)

    # Now fill in the values.
    subject_str = subject_str.format(**kwargs)

    return subject_str


# pylint: disable=too-many-branches
# pylint: disable=too-many-statements
def _parse_and_structure_results(**kwargs):
    """Parse the results and create a data structure for the templates.

    Create a special data structure to be consumed by the template engine.
    By default it will create the strings for TXT and HTML templates. The
    special template will then use the correct format.

    The template data structure is as follows:

        {
            "summary": {
                "txt": ["List of TXT summary strings"],
                "html: ["List of HTML summary strings"]
            },
            "data": {
                "arch": ["List of defconfigs"]
            }
        }

    :param failed_data: The failed data structure.
    :type failed_data: dictionary
    :param error_data: The error data structure.
    :type error_data: dictionary
    :param fail_count: The number of failures.
    :type fail_count: integer
    :param errors_count: The number of errors.
    :type errors_count: integer
    :param warnings_count: The number of warnings.
    :type warnings_count: integer
    :return The template data structure as a dictionary object.
    """
    platforms = {}
    k_get = kwargs.get
    error_data = k_get("error_data", None)
    errors_count = k_get("errors_count", 0)
    fail_count = k_get("fail_count", 0)
    failed_data = k_get("failed_data", None)
    warnings_count = k_get("warnings_count", 0)

    # Local substitutions dictionary, common to both data structures parsed.
    gen_subs = {
        "build_url": k_get("build_url"),
        "err_log_url": ERR_LOG_URL,
        "defconfig_url": DEFCONFIG_URL,
        "job": k_get("job"),
        "kernel": k_get("kernel"),
        "git_branch": k_get("git_branch"),
        "log_url": LOG_URL,
        "mism_log_url": MISM_LOG_URL,
        "red": rcommon.HTML_RED,
        "storage_url": k_get("storage_url"),
        "warn_log_url": WARN_LOG_URL,
        "yellow": rcommon.HTML_YELLOW
    }

    if failed_data:
        platforms["failed_data"] = {}
        platforms["failed_data"]["summary"] = {}
        platforms["failed_data"]["summary"]["txt"] = []
        platforms["failed_data"]["summary"]["html"] = []

        failure_summary = P_(
            u"Build Failure Detected:",
            u"Build Failures Detected:", fail_count)

        platforms["failed_data"]["summary"]["txt"].append(failure_summary)
        platforms["failed_data"]["summary"]["html"].append(failure_summary)
        platforms["failed_data"]["data"] = {}
        failed_struct = platforms["failed_data"]["data"]

        f_get = failed_data.get
        subs = gen_subs.copy()

        for arch in failed_data.viewkeys():
            subs["arch"] = arch
            arch_string = G_(u"{arch:s}:").format(**subs)
            failed_struct[arch_string] = []
            failed_append = failed_struct[arch_string].append

            for struct in f_get(arch):
                subs["defconfig"] = struct[0]
                subs["status"] = struct[1]
                if struct[2]:
                    subs["defconfig_url"] = DEFCONFIG_ID_URL
                    subs["build_id"] = struct[2]

                txt_str = G_(u"{defconfig:s}: {status:s}").format(**subs)
                html_str = (
                    DEFCONFIG_URL_HTML.format(**subs).format(**subs),
                    STATUS_HTML.format(**subs).format(**subs))
                failed_append((txt_str, html_str))
    else:
        platforms["failed_data"] = None

    if error_data:
        platforms["error_data"] = {}

        if errors_count > 0 and warnings_count > 0:
            summary_string = G_(u"Errors and Warnings Detected:")
        elif errors_count > 0 and warnings_count == 0:
            summary_string = G_(u"Errors Detected:")
        elif errors_count == 0 and warnings_count > 0:
            summary_string = G_(u"Warnings Detected:")

        platforms["error_data"]["summary"] = {}
        platforms["error_data"]["summary"]["txt"] = [summary_string]
        platforms["error_data"]["summary"]["html"] = [summary_string]

        if errors_count > 0 or warnings_count > 0:
            platforms["error_data"]["data"] = {}
            error_struct = platforms["error_data"]["data"]

            err_get = error_data.get
            subs = gen_subs.copy()

            for arch in error_data.viewkeys():
                subs["arch"] = arch
                arch_string = G_(u"{:s}:").format(arch)
                error_struct[arch_string] = []

                error_append = error_struct[arch_string].append

                # Force defconfigs to be sorted.
                defconfigs = list(err_get(arch).viewkeys())
                defconfigs.sort()

                for defconfig in defconfigs:
                    err_numb = err_get(arch)[defconfig].get(
                        models.ERRORS_KEY, 0)
                    warn_numb = err_get(arch)[defconfig].get(
                        models.WARNINGS_KEY, 0)
                    build_id = err_get(arch)[defconfig].get(
                        models.BUILD_ID_KEY)

                    if build_id:
                        subs["defconfig_url"] = DEFCONFIG_ID_URL
                        subs["build_id"] = build_id

                    err_string = P_(
                        u"{errors:d} error",
                        u"{errors:d} errors", err_numb)
                    warn_string = P_(
                        u"{warnings:d} warning",
                        u"{warnings:d} warnings", warn_numb)

                    subs["defconfig"] = defconfig
                    subs["err_string"] = err_string
                    subs["errors"] = err_numb
                    subs["warn_string"] = warn_string
                    subs["warnings"] = warn_numb

                    if err_numb > 0 and warn_numb > 0:
                        txt_desc_str = G_(
                            u"{err_string:s}, {warn_string:s}")
                        html_desc_str = (
                            ERR_STR_HTML.format(**subs).format(**subs),
                            WARN_STR_HTML.format(**subs).format(**subs)
                        )
                    elif err_numb > 0 and warn_numb == 0:
                        txt_desc_str = u"{err_string:s}"
                        html_desc_str = (
                            ERR_STR_HTML.format(**subs).format(**subs), u"")
                    elif err_numb == 0 and warn_numb > 0:
                        txt_desc_str = u"{warn_string:s}"
                        html_desc_str = (
                            u"", WARN_STR_HTML.format(**subs).format(**subs))

                    txt_desc_str = txt_desc_str.format(**subs)
                    subs["txt_desc_str"] = txt_desc_str

                    txt_defconfig_str = (
                        G_(u"{defconfig:s}: {txt_desc_str:s}").format(**subs)
                    ).format(**subs)
                    html_defconfing_str = (
                        DEFCONFIG_URL_HTML.format(**subs).format(**subs),
                        html_desc_str)

                    error_append((txt_defconfig_str, html_defconfing_str))
    else:
        platforms["error_data"] = None

    return platforms


def _create_build_email(**kwargs):
    """Parse the results and create the email text body to send.

    :param job: The name of the job.
    :type job: str
    :param  kernel: The name of the kernel.
    :type kernel: str
    :param git_commit: The git commit.
    :type git_commit: str
    :param git_url: The git url.
    :type git_url: str
    :param git_branch: The git branch.
    :type git_branch: str
    :param failed_data: The parsed failed results.
    :type failed_data: dict
    :param fail_count: The total number of failed results.
    :type fail_count: int
    :param total_count: The total number of results.
    :type total_count: int
    :param total_unique_data: The unique values data structure.
    :type total_unique_data: dictionary
    :param pass_count: The total number of passed results.
    :type pass_count: int
    :param base_url: The base URL to build the dashboard links.
    :type base_url: string
    :param boot_url: The base URL for the boot section of the dashboard.
    :type boot_url: string
    :param build_url: The base URL for the build section of the dashboard.
    :type build_url: string
    :param info_email: The email address for the footer note.
    :type info_email: string
    :return A tuple with the email body and subject as strings.
    """
    txt_body = None
    html_body = None
    subject_str = None

    k_get = kwargs.get
    email_format = k_get("email_format")
    total_unique_data = k_get("total_unique_data", None)
    failed_data = k_get("failed_data", None)
    error_data = k_get("error_data", None)

    subject_str = _get_build_subject_string(**kwargs)

    built_unique_one = G_(u"Built: {:s}")

    built_unique_string = None
    if total_unique_data:
        unique_archs = rcommon.count_unique(
            total_unique_data.get("arch", None))

        kwargs["unique_archs"] = unique_archs

        arch_str = P_(
            u"{unique_archs:d} unique architecture",
            u"{unique_archs:d} unique architectures",
            unique_archs
        )

        if unique_archs > 0:
            built_unique_string = built_unique_one.format(arch_str)

        if built_unique_string:
            built_unique_string = built_unique_string.format(**kwargs)

    build_summary_url = BUILD_SUMMARY_URL.format(**kwargs)

    kwargs["built_unique_string"] = built_unique_string
    kwargs["tree_string"] = G_(u"Tree: {job:s}").format(**kwargs)
    kwargs["branch_string"] = G_(u"Branch: {git_branch:s}").format(**kwargs)
    kwargs["git_describe_string"] = G_(u"Git Describe: {kernel:s}").format(
        **kwargs)
    kwargs["subject_str"] = subject_str

    git_url = k_get("git_url")
    git_commit = k_get("git_commit")

    translated_git_url = \
        rcommon.translate_git_url(git_url, git_commit) or git_url

    git_txt_string = G_(u"Git URL: {:s}").format(git_url)
    git_html_string = G_(u"Git URL: <a href=\"{:s}\">{:s}</a>").format(
        translated_git_url, git_url)

    kwargs["git_commit_string"] = G_(u"Git Commit: {:s}").format(git_commit)
    kwargs["git_url_string"] = (git_txt_string, git_html_string)

    if failed_data or error_data:
        kwargs["platforms"] = _parse_and_structure_results(**kwargs)

    if models.EMAIL_TXT_FORMAT_KEY in email_format:
        kwargs["full_build_summary"] = (
            G_(u"Full Build Summary: {:s}").format(build_summary_url))

        txt_body = rcommon.create_txt_email("build.txt", **kwargs)

    if models.EMAIL_HTML_FORMAT_KEY in email_format:
        # Fix the summary URLs for the HTML email.
        kwargs["full_build_summary"] = (
            G_(u"Full Build Summary: <a href=\"{url:s}\">{url:s}</a>").format(
                **{"url": build_summary_url}))

        html_body = rcommon.create_html_email("build.html", **kwargs)

    return txt_body, html_body, subject_str


def create_build_report(
        job,
        branch, kernel, email_format, db_options, mail_options=None):
    """Create the build report email to be sent.

    :param job: The name of the job.
    :type job: str
    :param  kernel: The name of the kernel.
    :type kernel: str
    :param email_format: The email format to send.
    :type email_format: list
    :param db_options: The mongodb database connection parameters.
    :type db_options: dict
    :param mail_options: The options necessary to connect to the SMTP server.
    :type mail_options: dict
    :return A tuple with the email body and subject as strings or None.
    """
    kwargs = {}
    txt_body = None
    html_body = None
    subject = None
    # This is used to provide a footer note in the email report.
    info_email = None

    fail_count = total_count = 0
    errors_count = warnings_count = 0
    fail_results = []

    if mail_options:
        info_email = mail_options.get("info_email", None)

    spec = {
        models.JOB_KEY: job,
        models.GIT_BRANCH_KEY: branch,
        models.KERNEL_KEY: kernel
    }

    database = utils.db.get_db_connection(db_options)
    total_results, total_count = utils.db.find_and_count(
        database[models.BUILD_COLLECTION],
        0,
        0,
        spec=spec,
        fields=BUILD_SEARCH_FIELDS
    )

    err_data, errors_count, warnings_count = _get_errors_count(
        total_results.clone())

    compiler_aggregate = database[models.BUILD_COLLECTION].aggregate([
        {"$match": spec},
        {
            "$group": {
                "_id": "${:s}".format(models.ARCHITECTURE_KEY),
                "compiler": {
                    "$addToSet":
                        "${:s}".format(models.COMPILER_VERSION_FULL_KEY)
                }
            }
        }
    ])

    compiler_data = {}
    for data in compiler_aggregate["result"]:
        compiler_data[data["_id"]] = data["compiler"]

    total_unique_data = rcommon.get_unique_data(
        total_results.clone(), unique_keys=[models.ARCHITECTURE_KEY])

    spec[models.STATUS_KEY] = models.FAIL_STATUS

    fail_results, fail_count = utils.db.find_and_count(
        database[models.BUILD_COLLECTION],
        0,
        0,
        spec=spec,
        fields=BUILD_SEARCH_FIELDS,
        sort=BUILD_SEARCH_SORT)

    failed_data = _parse_build_data(fail_results.clone())

    # Retrieve the parsed errors/warnings/mismatches summary and then
    # the details.
    errors_spec = {
        models.JOB_KEY: job,
        models.GIT_BRANCH_KEY: branch,
        models.KERNEL_KEY: kernel
    }
    errors_summary = utils.db.find_one2(
        database[models.ERRORS_SUMMARY_COLLECTION],
        errors_spec,
        fields=[
            models.ERRORS_KEY, models.WARNINGS_KEY, models.MISMATCHES_KEY
        ]
    )

    error_details = utils.db.find(
        database[models.ERROR_LOGS_COLLECTION],
        0,
        0,
        spec=errors_spec,
        sort=[(models.DEFCONFIG_FULL_KEY, 1)]
    )
    error_details = [d for d in error_details.clone()]

    kwargs = {
        "base_url": rcommon.DEFAULT_BASE_URL,
        "build_url": rcommon.DEFAULT_BUILD_URL,
        "compiler_data": compiler_data,
        "email_format": email_format,
        "error_data": err_data,
        "error_details": error_details,
        "errors_count": errors_count,
        "errors_summary": errors_summary,
        "fail_count": fail_count,
        "failed_data": failed_data,
        "info_email": info_email,
        "pass_count": total_count - fail_count,
        "storage_url": rcommon.DEFAULT_STORAGE_URL,
        "total_count": total_count,
        "total_unique_data": total_unique_data,
        "warnings_count": warnings_count,
        "git_branch": branch,
        models.JOB_KEY: job,
        models.KERNEL_KEY: kernel,
    }

    kwargs["git_commit"], kwargs["git_url"] = \
        rcommon.get_git_data(job, branch, kernel, db_options)

    custom_headers = {
        rcommon.X_REPORT: rcommon.BUILD_REPORT_TYPE,
        rcommon.X_BRANCH: branch,
        rcommon.X_TREE: job,
        rcommon.X_KERNEL: kernel,
    }

    if all([fail_count == 0, total_count == 0]):
        utils.LOG.warn(
            "Nothing found for '%s-%s-%s': no build email report sent",
            job, branch, kernel)
    else:
        txt_body, html_body, subject = _create_build_email(**kwargs)

    return txt_body, html_body, subject, custom_headers
