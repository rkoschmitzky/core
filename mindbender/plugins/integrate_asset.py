import pyblish.api


class IntegrateMindbenderAsset(pyblish.api.InstancePlugin):
    """Move user data to shared location

    This plug-in exposes your data to others by encapsulating it
    into a new version.

    Schema:
        Data is written in the following format.
         ____________________
        |                    |
        | version            |
        |  ________________  |
        | |                | |
        | | representation | |
        | |________________| |
        | |                | |
        | | ...            | |
        | |________________| |
        |____________________|

    """

    label = "Integrate Mindbender Asset"
    order = pyblish.api.IntegratorOrder
    families = [
        "mindbender.model",
        "mindbender.rig",
        "mindbender.animation",
        "mindbender.lookdev",
    ]

    def process(self, instance):
        import os
        import json
        import errno
        import shutil
        from mindbender import api

        assert os.getenv("ASSETDIR"), (
            "Missing environment variable ASSETDIR\n"
            "This can sometimes happen when an application was launched \n"
            "manually, outside of the pipeline."
        )

        assert os.getenv("MINDBENDER_SILO"), (
            "Missing environment variable MINDBENDER_SILO\n"
            "This can sometimes happen when an application was launched \n"
            "manually, outside of the pipeline."
        )

        context = instance.context

        # Atomicity
        #
        # Guarantee atomic publishes - each asset contains
        # an identical set of members.
        #     __
        #    /     o
        #   /       \
        #  |    o    |
        #   \       /
        #    o   __/
        #
        assert all(result["success"] for result in context.data["results"]), (
            "Atomicity not held, aborting.")

        # Assemble
        #
        #       |
        #       v
        #  --->   <----
        #       ^
        #       |
        #
        stagingdir = instance.data.get("stagingDir")
        assert stagingdir, (
            "Incomplete instance \"%s\": "
            "Missing reference to staging area."
            % instance
        )

        self.log.debug("Establishing staging directory @ %s" % stagingdir)

        root = os.getenv("ASSETDIR")
        instancedir = os.path.join(root, "publish", instance.data["subset"])

        try:
            os.makedirs(instancedir)
        except OSError as e:
            if e.errno != errno.EEXIST:  # Already exists
                self.log.critical("An unexpected error occurred.")
                raise

        version = api.find_latest_version(os.listdir(instancedir)) + 1
        versiondir = os.path.join(instancedir, api.format_version(version))

        self.log.debug("New version: %i" % version)

        # Metadata
        #  _________
        # |         |.key = value
        # |         |
        # |         |
        # |         |
        # |         |
        # |_________|
        #
        fname = os.path.join(stagingdir, ".metadata.json")

        try:
            with open(fname) as f:
                metadata = json.load(f)

        except IOError:
            metadata = {
                "schema": "mindbender-core:version-1.0",
                "version": version,
                "path": os.path.join(
                    "{root}",
                    os.path.relpath(
                        versiondir,
                        api.registered_root()
                    )
                ).replace("\\", "/"),
                "representations": list(),

                # Used to identify family of assets already on disk
                "families": instance.data.get("families", list()) + [
                    instance.data.get("family")
                ],

                "time": context.data["time"],
                "author": context.data["user"],

                # Record within which silo this asset was made.
                "silo": os.environ["MINDBENDER_SILO"],

                # Collected by pyblish-maya
                "source": os.path.join(
                    "{root}",
                    os.path.relpath(
                        context.data["currentFile"],
                        api.registered_root()
                    )
                ).replace("\\", "/"),
            }

        self.log.debug("Finished generating metadata: %s"
                       % json.dumps(metadata, indent=4))

        for filename in instance.data.get("files", list()):
            name, ext = os.path.splitext(filename)
            metadata["representations"].append(
                {
                    "schema": "mindbender-core:representation-1.0",
                    "format": ext,
                    "path": os.path.join(
                        "{dirname}",
                        "%s{format}" % name,
                    ).replace("\\", "/")
                }
            )

        # Write to disk
        #          _
        #         | |
        #        _| |_
        #    ____\   /
        #   |\    \ / \
        #   \ \    v   \
        #    \ \________.
        #     \|________|
        #
        with open(fname, "w") as f:
            json.dump(metadata, f, indent=4)

        # Metadata is written before being validated -
        # this way, if validation fails, the data can be
        # inspected by hand from within the user directory.
        api.schema.validate(metadata, "version")
        shutil.copytree(stagingdir, versiondir)

        self.log.info("Successfully integrated \"%s\" to \"%s\"" % (
            instance, versiondir))
