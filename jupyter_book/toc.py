"""A small sphinx extension to use a global table of contents"""
import os
import yaml
from textwrap import dedent
from pathlib import Path


def _no_suffix(path):
    if isinstance(path, str):
        path = str(Path(path).with_suffix(""))
    return path


def find_name(pages, name):
    """
    Takes a dict with nested lists and dicts,
    and searches all dicts for a key of the field
    provided.
    """
    page = None
    if isinstance(pages, dict):
        pages = [pages]

    for page in pages:
        if _no_suffix(page.get("path")) == name:
            return page
        else:
            sections = page.get("sections", [])
            page = find_name(sections, name)
            if page is not None:
                return page


def add_toctree(app, docname, source):
    # If no globaltoc is given, we'll skip this part
    if not app.config["globaltoc_path"]:
        return
    
    # First check whether this page has any descendants
    # If so, then we'll manually add them as a toctree object
    path = app.env.doc2path(docname, base=None)
    toc = app.config["globaltoc"]
    page = find_name(toc, _no_suffix(path))

    # If we didn't find this page in the TOC, raise an error
    if page is None:
        raise FileNotFoundError(f"The following path in your table of contents couldn't be found:\n\n{path}.\n\nDouble check your `_toc.yml` file to make sure the paths are correct.")

    # If we have no sections, then don't worry about a toctree
    sections = [(ii.get("path"), ii.get("name")) for ii in page.get("sections", [])]
    if len(sections) == 0:
        return

    for ii, (path_sec, name) in enumerate(sections):
        # Update path so it is relative to the root of the parent
        path_parent_folder = Path(page["path"]).parent
        path_sec = os.path.relpath(path_sec, path_parent_folder)

        # Decide whether we'll over-ride with a name in the toctree
        this_section = f"{path_sec}"
        if name:
            this_section = f"{name} <{this_section}>"
        sections[ii] = this_section

    # Parse the options block
    options = page.get("options", [])
    if isinstance(options, str):
        options = [options]
    options = "\n".join([f":{ii}:" for ii in options])

    # Figure out what kind of text defines a toctree directive for this file
    # currently, assumed to be markdown
    suff = Path(path).suffix
    toctree_text = dedent(
        """
    ```{{toctree}}
    :hidden:
    :titlesonly:
    {options}

    {sections}
    ```
    """
    )

    # Create the markdown directive for our toctree
    toctree = toctree_text.format(options=options, sections="\n".join(sections))
    if suff == ".md":
        source[0] += toctree + "\n"
    elif suff == ".ipynb":
        # Lazy import nbformat because we only need it if we have an ipynb file
        import nbformat as nbf

        ntbk = nbf.reads(source[0], nbf.NO_CONVERT)
        md = nbf.v4.new_markdown_cell(toctree)
        ntbk.cells.append(md)
        source[0] = nbf.writes(ntbk)
    else:
        raise ValueError("Only markdown and ipynb files are supported.")


def update_indexname(app, config):
    # If no globaltoc is given, we'll skip this part
    if not app.config["globaltoc_path"]:
        return

    # Load the TOC and update the env so we have it later
    toc = yaml.safe_load(Path(app.config["globaltoc_path"]).read_text())
    if isinstance(toc, list):
        toc_updated = toc[0]
        if len(toc) > 1:
            subsections = toc[1:]
            toc_updated["sections"] = subsections
    app.config["globaltoc"] = toc_updated

    # Update the main toctree file for whatever the first file here is
    app.config["master_doc"] = _no_suffix(toc_updated["path"])

    
    
##############################################
# Auto-generating a `_toc.yml` file.

SUPPORTED_FILE_SUFFIXES = ['.ipynb', '.md', ".markdown", ".Rmd", ".py", "#BREAK#"]

def _filename_to_title(filename, split_char='_'):
    """Convert a file path into a more readable title."""
    filename = Path(filename).with_suffix('').name
    filename_parts = filename.split(split_char)
    try:
        # If first part of the filename is a number for ordering, remove it
        int(filename_parts[0])
        if len(filename_parts) > 1:
            filename_parts = filename_parts[1:]
    except Exception:
        pass
    title = ' '.join(ii.capitalize() for ii in filename_parts)
    return title

DESCRIPTION = ("Automatically generate a _toc.yaml file from a collection"
               " of Jupyter Notebooks/markdown files that make a jupyter book."
               " The alpha-numeric name of folders/files will be used to choose the order of chapters."
               " This is just a helper script, it will likely not generate YAML that will create a "
               " valid Jupyter Book. Use it as a time-saver, not a total solution for making a TOC.")

YAML_TOP = ("# Each entry has the following schema:\n"
            "#\n"
            "# - title: mytitle   # Title of chapter or section\n"
            "#   url: /myurl  # URL of section relative to the /content/ folder.\n"
            "#   sections:  # Contains a list of more entries that make up the chapter's sections\n"
            "#   not_numbered: true  # if the section shouldn't have a number in the sidebar\n"
            "#     (e.g. Introduction or appendices)\n"
            "#   expand_sections: true  # if you'd like the sections of this chapter to always\n"
            "#     be expanded in the sidebar.\n"
            "#   external: true  # Whether the URL is an external link or points to content in the book\n"
            "#\n"
            "# Below are some special values that trigger specific behavior:\n"
            "# - search: true  # Will provide a link to a search page\n"
            "# - divider: true  # Will insert a divider in the sidebar\n"
            "# - header: My Header  # Will insert a header with no link in the sidebar\n")

YAML_WARN = ("#\n"
             "# ==============================\n"
             "# AUTOMATICALLY GENERATED TOC FILE.\n"
             "# You should review the contents of this file, re-order items as you wish,\n"
             "# and nest chapters in sections if you wish. The ======= symbols represent \n"
             "# folder breaks.\n"
             "# \n"
             "# See the demo `toc.yml` for the right structure to follow. You can \n"
             "# generate a demo book by running `jupyter-book create mybook --demo`\n"
             "# ==============================\n\n\n")


def _list_supported_files(directory, exclude=["LICENSE.md"], rglob=False):
    glob = directory.rglob if rglob is True else directory.glob
    supported_files = [
        ipath for suffix in SUPPORTED_FILE_SUFFIXES
        for ipath in glob(f"*{suffix}")
        if (ipath.name not in exclude) and ('ipynb_checkpoints' not in str(ipath))
    ]
    return supported_files


def build_toc(content_folder, filename_split_char='_'):
    """Auto-generate a Table of Contents from files/folders.

    Parameters
    ----------
    content_folder : str
        Path to the folder where content exists. The TOC will be generated
        according to the alphanumeric sort of these files/folders.
    filename_split_char : str
        The character used in inferring spaces in page names from filenames.
    """
    content_folder = Path(content_folder)
    if not content_folder.is_dir():
        raise ValueError(f"Could not find the provided content folder\n{content_folder}")

    # Generate YAML from the directory structure
    out = [YAML_TOP, YAML_WARN]
    toc_pages = []

    # First find all the allowed file types in path
    paths = _list_supported_files(content_folder)
    for ipath in paths:
        ipath = ipath.with_suffix('')
        path = str(Path(*ipath.parts[1:]))
        toc_pages.append({'path': path})

    # Now find all the top-level directories of the content folder
    subdirectories = sorted([sub for sub in content_folder.glob('*')
                             if (sub.is_dir() and '.ipynb_checkpoints' not in sub.name)])

    for subdir in subdirectories:
        ipaths = _list_supported_files(subdir, rglob=True)
        if len(ipaths) == 0:
            continue

        # Add a section break for this section
        toc_pages.append("## REPLACE ##")
        toc_pages.append({'header': _filename_to_title(subdir.name, filename_split_char)})

        # Now add the children as a list of pages
        for ipath in ipaths:
            ipath = ipath.with_suffix('')
            url = str(Path(*ipath.parts[1:]))
            toc_pages.append({'url': url})
    import IPython; IPython.embed()
    # Convert the dictionary into YAML and append it to our output
    out = yaml.safe_dump(toc_pages).replace("- '## REPLACE ##'", '')
    return '\n'.join(out)