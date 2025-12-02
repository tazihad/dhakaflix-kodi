#!/usr/bin/env python

# This script zips add-on folders and generates the addons.xml and addons.xml.md5 files for a Kodi repository.
# It should be run from the root directory of your repository.

import os
import shutil
import hashlib
import zipfile
import re

class Generator:
    """
    Generates a new addons.xml file from each add-on's addon.xml file
    and creates a new addons.xml.md5 hash file. Must be run from the root
    of the checked-out repo. Only handles single-depth folder structure.
    """

    def __init__(self):
        # The directory where zipped add-ons and XML index files will be stored
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
        addons_xml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<addons>\n'
        
        # Get a list of all folders in the current directory (should be add-ons)
        addons = os.listdir(".")
        
        # Loop through each folder to find add-ons
        for addon_id in addons:
            # Ignore the zips folder, docs, and hidden files
            if os.path.isdir(addon_id) and not addon_id.startswith('.') and addon_id != self.ADDONS_DIR:
                
                addon_xml_path = os.path.join(addon_id, "addon.xml")
                
                if os.path.exists(addon_xml_path):
                    try:
                        print(f"  Processing {addon_id}...")
                        
                        # Read the addon.xml file
                        with open(addon_xml_path, "r", encoding="utf-8") as f:
                            xml_lines = f.readlines()

                        addon_xml_content = ""
                        version = None
                        
                        # Loop through lines to find the version and extract the XML content
                        for line in xml_lines:
                            # Skip XML preamble and unnecessary lines
                            if '<?xml' in line or '<addon-dependency>' in line:
                                continue

                            # Extract version number
                            if 'version="' in line and version is None:
                                version_match = re.search(r'version="(.+?)"', line)
                                if version_match:
                                    version = version_match.group(1)

                            # Append the line to the collective XML, preserving indentation
                            addon_xml_content += line.rstrip() + "\n"
                        
                        # Add the addon XML content to the master XML structure
                        addons_xml += addon_xml_content.strip() + "\n\n"
                        
                        # Create the zip file for the add-on
                        if version:
                            self._create_zip(addon_id, version)
                        else:
                            print(f"    WARNING: Could not find version for {addon_id}. Skipping zip creation.")

                    except Exception as e:
                        print(f"    ERROR: Excluding {addon_id} due to processing error: {e}")

        # Close the master XML structure
        addons_xml += '</addons>\n'
        
        # Write the final addons.xml file to the zips directory
        with open(os.path.join(self.ADDONS_DIR, "addons.xml"), "w", encoding="utf-8") as f:
            f.write(addons_xml)
        
        print("addons.xml written.")

    def _create_zip(self, addon_id, version):
        """
        Creates a zip file for the given add-on.
        """
        zip_filename = f"{addon_id}-{version}.zip"
        zip_path = os.path.join(self.ADDONS_DIR, zip_filename)

        print(f"    Creating {zip_filename}...")
        
        # Check if the zip already exists and is current.
        if os.path.exists(zip_path):
            # Check if the existing zip is newer than the source folder (simple check)
            zip_time = os.path.getmtime(zip_path)
            source_time = os.path.getmtime(addon_id)
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
                # Exclude hidden files/folders and specific source files
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('_pycache__')]
                
                for file in files:
                    if not file.startswith('.') and not file.endswith('.pyc'):
                        full_path = os.path.join(root, file)
                        # Add the file to the zip, preserving the add-on folder as the root of the zip
                        archive_name = os.path.join(root, file)
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