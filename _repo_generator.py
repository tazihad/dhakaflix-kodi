#!/usr/bin/env python
# Final script updated to create the nested folder structure inside /zips/
# Example: zips/plugin.video.dhakaflix/plugin.video.dhakaflix-1.0.0.zip

import os
import shutil
import hashlib
import zipfile
import xml.etree.ElementTree as ET

class Generator:
    """
    Generates a new addons.xml file from each add-on's addon.xml file
    and creates a new addons.xml.md5 hash file.
    """

    def __init__(self):
        # The directory where zipped add-ons and XML index files are stored
        self.ADDONS_DIR = "zips"

        if not os.path.exists(self.ADDONS_DIR):
            os.makedirs(self.ADDONS_DIR)

        self._generate_addons_file()
        self._generate_md5_file()
        print("\nRepository generation finished successfully!")

    def _generate_addons_file(self):
        """
        Generates the master addons.xml file from the individual addon.xml files.
        """
        print("\nGenerating addons.xml...")

        # Start the master XML file structure
        addons_xml = ET.Element('addons')

        # Loop through each folder to find add-ons
        for addon_id in sorted(os.listdir(".")):

            addon_xml_path = os.path.join(addon_id, "addon.xml")

            # Check if it's a valid add-on directory
            if os.path.isdir(addon_id) and addon_id != self.ADDONS_DIR and os.path.exists(addon_xml_path):

                try:
                    print(f"  Processing {addon_id}...")

                    # Parse the individual addon.xml file
                    tree = ET.parse(addon_xml_path)
                    root = tree.getroot()

                    if root.tag == 'addon':
                        version = root.get('version')

                        if version:
                            # Add the entire <addon> element to the master XML structure
                            addons_xml.append(root)

                            # Create the zip file for the add-on in the NEW nested folder
                            self._create_zip(addon_id, version)
                        else:
                            print(f"    WARNING: Skipping {addon_id}. Missing 'version' attribute in addon.xml.")

                except Exception as e:
                    print(f"    ERROR: Excluding {addon_id} due to processing error: {e}")

        # Write the final addons.xml file to the zips directory
        output_xml_path = os.path.join(self.ADDONS_DIR, "addons.xml")
        try:
            # Use to_xml to format the output with the XML declaration
            with open(output_xml_path, "wb") as f:
                f.write(ET.tostring(addons_xml, encoding='utf-8', xml_declaration=True))

            # Post-processing to add standalone="yes" for Kodi compatibility
            with open(output_xml_path, "r", encoding='utf-8') as f:
                content = f.read()
            content = content.replace("<?xml version='1.0' encoding='utf-8'?>", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>', 1)

            with open(output_xml_path, "w", encoding='utf-8') as f:
                f.write(content)

            print("addons.xml written.")

        except Exception as e:
            print(f"ERROR: Failed to write addons.xml: {e}")


    def _create_zip(self, addon_id, version):
        """
        Creates a zip file for the given add-on, placing it in zips/[ADDON ID]/
        """
        zip_filename = f"{addon_id}-{version}.zip"

        # --- NEW CODE START ---
        # Define the path to the NEW nested folder: zips/addon_id/
        nested_dir = os.path.join(self.ADDONS_DIR, addon_id)
        if not os.path.exists(nested_dir):
            os.makedirs(nested_dir)

        # Define the full zip path: zips/addon_id/addon_id-x.x.x.zip
        zip_path = os.path.join(nested_dir, zip_filename)
        # --- NEW CODE END ---

        print(f"    Creating {zip_filename} inside {nested_dir}...")

        # Check if the zip already exists and is current (based on timestamp)
        if os.path.exists(zip_path):
            zip_time = os.path.getmtime(zip_path)
            source_time = os.path.getmtime(os.path.join(addon_id, "addon.xml"))

            for root, dirs, files in os.walk(addon_id):
                for name in files:
                    source_time = max(source_time, os.path.getmtime(os.path.join(root, name)))

            if source_time < zip_time:
                print(f"    Skipping: {zip_filename} is up to date.")
                return
            else:
                os.remove(zip_path)

        try:
            # Create the zip file
            zf = zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED)

            # Walk through the add-on directory
            for root, dirs, files in os.walk(addon_id):
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('__pycache__', '.git', '.github')]

                for file in files:
                    if not file.startswith('.') and not file.endswith('.pyc'):
                        full_path = os.path.join(root, file)
                        archive_name = os.path.join(addon_id, os.path.relpath(full_path, addon_id))
                        zf.write(full_path, archive_name)

            zf.close()
            print(f"    {zip_filename} created successfully.")

        except Exception as e:
            print(f"    ERROR: Failed to create zip for {addon_id}: {e}")
            if os.path.exists(zip_path):
                os.remove(zip_path)

    def _generate_md5_file(self):
        """
        Generates the MD5 hash file for the addons.xml file.
        """
        print("Generating addons.xml.md5...")

        addons_xml_path = os.path.join(self.ADDONS_DIR, "addons.xml")
        md5_path = os.path.join(self.ADDONS_DIR, "addons.xml.md5")

        try:
            with open(addons_xml_path, 'rb') as f:
                md5_hash = hashlib.md5(f.read()).hexdigest()

            with open(md5_path, 'w') as f:
                f.write(md5_hash)

            print("addons.xml.md5 written.")

        except Exception as e:
            print(f"ERROR: Failed to create md5 hash: {e}")

if __name__ == "__main__":
    Generator()
