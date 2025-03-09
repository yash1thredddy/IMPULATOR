"""
3D Molecular visualization module using py3Dmol and RDKit.
"""
import os
import json
import logging
from typing import Dict, Optional, Union, List

import streamlit as st
from rdkit import Chem
from rdkit.Chem import AllChem

from config import MOLECULE_3D_STYLE, MOLECULE_COLORS, MOLECULE_2D_SIZE

# Configure logging
logger = logging.getLogger(__name__)

def generate_3d_coordinates(smiles: str, optimize: bool = True) -> Optional[Chem.Mol]:
    """
    Generate 3D coordinates for a molecule from SMILES.
    
    Args:
        smiles: SMILES string of the molecule
        optimize: Whether to optimize coordinates with MMFF
    
    Returns:
        Optional[Chem.Mol]: Molecule with 3D coordinates or None if failed
    """
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        
        # Add hydrogens
        mol_3d = Chem.AddHs(mol)
        
        # Generate 3D coordinates
        AllChem.EmbedMolecule(mol_3d, randomSeed=42)
        
        # Optimize if requested
        if optimize:
            try:
                AllChem.MMFFOptimizeMolecule(mol_3d)
            except:
                logger.warning(f"MMFF optimization failed for {smiles}, trying UFF")
                try:
                    AllChem.UFFOptimizeMolecule(mol_3d)
                except:
                    logger.warning(f"UFF optimization failed for {smiles}, using unoptimized coordinates")
        
        return mol_3d
    except Exception as e:
        logger.error(f"Error generating 3D coordinates: {str(e)}")
        return None

def get_molecule_style_controls() -> Dict:
    """
    Create UI controls for molecule style.
    
    Returns:
        Dict: Dictionary of style settings
    """
    st.sidebar.subheader("Molecule Visualization Settings")
    
    # Visualization style
    style_options = ["stick", "line", "cross", "sphere", "cartoon"]
    style = st.sidebar.selectbox(
        "Visualization Style:",
        style_options,
        index=style_options.index(MOLECULE_3D_STYLE) if MOLECULE_3D_STYLE in style_options else 0
    )
    
    # Additional settings based on style
    style_settings = {"style": style}
    
    if style == "stick":
        style_settings["radius"] = st.sidebar.slider("Stick Radius:", 0.1, 1.0, 0.3, 0.05)
    elif style == "sphere":
        style_settings["radius"] = st.sidebar.slider("Sphere Radius:", 0.5, 3.0, 1.2, 0.1)
    
    # Color scheme
    coloring_options = ["element", "residue", "spectrum"]
    coloring = st.sidebar.selectbox("Coloring Scheme:", coloring_options)
    style_settings["coloring"] = coloring
    
    # Surface options
    if st.sidebar.checkbox("Show Surface", False):
        surface_options = ["VDW", "SAS", "MS"]
        surface_type = st.sidebar.selectbox("Surface Type:", surface_options)
        opacity = st.sidebar.slider("Surface Opacity:", 0.1, 1.0, 0.5, 0.05)
        style_settings["surface"] = {
            "type": surface_type,
            "opacity": opacity
        }
    
    # Background color
    bg_color_options = ["white", "black", "grey"]
    style_settings["background"] = st.sidebar.selectbox("Background Color:", bg_color_options)
    
    return style_settings

def view_molecule_3d(
    mol_or_pdb: Union[Chem.Mol, str],
    height: int = 500,
    width: str = "100%",
    style_settings: Optional[Dict] = None
) -> None:
    """
    Display a 3D molecular visualization using py3Dmol.
    
    Args:
        mol_or_pdb: RDKit molecule or PDB block string
        height: Height of the viewer in pixels
        width: Width of the viewer (CSS value)
        style_settings: Dictionary of style settings
    """
    try:
        # Use default style settings if none provided
        if style_settings is None:
            style_settings = {
                "style": MOLECULE_3D_STYLE,
                "coloring": "element",
                "background": "white"
            }
        
        # Convert RDKit mol to PDB if needed
        if isinstance(mol_or_pdb, Chem.Mol):
            pdb_block = Chem.MolToPDBBlock(mol_or_pdb)
        else:
            pdb_block = mol_or_pdb
        
        # Escape any backticks in the PDB string (needed for JavaScript template)
        pdb_block = pdb_block.replace("`", "\\`")
        
        # Create style options JSON for 3Dmol.js
        style_obj = {}
        if style_settings["style"] == "stick":
            style_obj = {"stick": {"radius": style_settings.get("radius", 0.3)}}
        elif style_settings["style"] == "sphere":
            style_obj = {"sphere": {"radius": style_settings.get("radius", 1.2)}}
        elif style_settings["style"] == "line":
            style_obj = {"line": {}}
        elif style_settings["style"] == "cross":
            style_obj = {"cross": {"lineWidth": 2}}
        elif style_settings["style"] == "cartoon":
            style_obj = {"cartoon": {}}
        
        # Coloring
        if style_settings["coloring"] == "element":
            # No need to modify style_obj, element is default
            pass
        elif style_settings["coloring"] == "residue":
            style_obj["colorByResidue"] = True
        elif style_settings["coloring"] == "spectrum":
            style_obj["colorScheme"] = "spectrum"
        
        # Convert to JSON string for JavaScript
        style_json = json.dumps(style_obj)
        
        # Surface settings
        surface_code = ""
        if "surface" in style_settings:
            surface_type = style_settings["surface"]["type"]
            opacity = style_settings["surface"]["opacity"]
            surface_code = f'viewer.addSurface($3Dmol.SurfaceType.{surface_type}, {{opacity: {opacity}}});'
        
        # Create HTML component for 3Dmol viewer
        html_content = f"""
        <script src="https://cdnjs.cloudflare.com/ajax/libs/3Dmol/2.0.1/3Dmol-min.js"></script>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/jquery/3.6.3/jquery.min.js"></script>
        <style>
            .mol-container {{
                width: {width};
                height: {height}px;
                position: relative;
            }}
        </style>
        <div id="3dmol-viewer" class="mol-container"></div>
        <script>
            let viewer = $3Dmol.createViewer($("#3dmol-viewer"), {{backgroundColor: "{style_settings['background']}"}});
            let pdbData = `{pdb_block}`;
            viewer.addModel(pdbData, "pdb");
            viewer.setStyle({{}}, {style_json});
            {surface_code}
            viewer.zoomTo();
            viewer.render();
        </script>
        """
        
        # Display HTML in Streamlit
        st.components.v1.html(html_content, height=height+50)
    
    except Exception as e:
        logger.error(f"Error displaying 3D molecule: {str(e)}")
        st.error(f"Failed to display 3D molecule: {str(e)}")

def view_molecule_from_smiles(
    smiles: str,
    height: int = 500,
    width: str = "100%",
    style_settings: Optional[Dict] = None,
    optimize: bool = True
) -> None:
    """
    Display a 3D molecular visualization from SMILES string.
    
    Args:
        smiles: SMILES string of the molecule
        height: Height of the viewer in pixels
        width: Width of the viewer (CSS value)
        style_settings: Dictionary of style settings
        optimize: Whether to optimize coordinates with MMFF
    """
    mol_3d = generate_3d_coordinates(smiles, optimize)
    if mol_3d:
        view_molecule_3d(mol_3d, height, width, style_settings)
    else:
        st.error(f"Failed to generate 3D structure for SMILES: {smiles}")

# Update in molecule_viewer_app function in molecule_viewer.py
def molecule_viewer_app(compound_folder: str) -> None:
    """
    Main function for the molecular viewer application.
    
    Args:
        compound_folder: Path to the compound folder
    """
    try:
        structure_folder = os.path.join(compound_folder, "Structures")
        structure_info_path = os.path.join(structure_folder, "structure_info.json")
        
        if not os.path.exists(structure_info_path):
            st.warning("No structure information available for this compound.")
            return
        
        with open(structure_info_path, 'r') as f:
            structure_info = json.load(f)
        
        if not structure_info:
            st.warning("No molecular structures available for this compound.")
            return
        
        # Get style settings from sidebar
        style_settings = get_molecule_style_controls()
        
        # Main content area
        col1, col2 = st.columns([1, 2])
        
        with col1:
            # Create a dropdown to select molecules
            selected_molecule = st.selectbox(
                "Select Molecule:",
                options=[f"{mol['ChEMBL ID']} - {mol['Molecule Name']}" for mol in structure_info],
                key="viewer_molecule_selector"
            )
            
            # Get selected molecule info
            selected_idx = next((i for i, mol in enumerate(structure_info) 
                               if f"{mol['ChEMBL ID']} - {mol['Molecule Name']}" == selected_molecule), 0)
            mol_data = structure_info[selected_idx]
            
            # Display molecule info
            st.subheader("Molecule Information")
            st.write(f"**ChEMBL ID:** {mol_data['ChEMBL ID']}")
            st.write(f"**Name:** {mol_data['Molecule Name']}")
            st.write(f"**Formula:** {mol_data['Formula']}")
            if mol_data['Exact Mass']:
                st.write(f"**Exact Mass:** {mol_data['Exact Mass']:.4f}")
            st.write(f"**SMILES:** `{mol_data['SMILES']}`")
            
            # Add download options with a unique key
            st.download_button(
                "Download Structure Data (JSON)",
                data=json.dumps(mol_data, indent=2),
                file_name=f"{mol_data['ChEMBL ID']}_structure.json",
                mime="application/json",
                key=f"viewer_download_{mol_data['ChEMBL ID']}"
            )
            
            # Display 2D structure
            st.subheader("2D Structure")
            img_path = os.path.join(structure_folder, mol_data['2D_Image'])
            if os.path.exists(img_path):
                # Updated to use_container_width instead of use_column_width
                st.image(img_path, use_container_width=True)
            else:
                st.warning("2D structure image not available.")
        
        with col2:
            st.subheader("3D Structure")
            
            # Option to regenerate 3D structure
            regenerate = st.checkbox("Regenerate 3D coordinates on-the-fly", value=False)
            
            if regenerate:
                # Generate 3D structure directly from SMILES
                view_molecule_from_smiles(
                    mol_data['SMILES'],
                    height=500,
                    style_settings=style_settings,
                    optimize=True
                )
            else:
                # Use pre-generated PDB file
                pdb_path = os.path.join(structure_folder, mol_data['3D_Model'])
                if os.path.exists(pdb_path):
                    with open(pdb_path, 'r') as f:
                        pdb_block = f.read()
                    view_molecule_3d(pdb_block, height=500, style_settings=style_settings)
                else:
                    st.warning("3D structure model not available. Try regenerating from SMILES.")
    
    except Exception as e:
        logger.error(f"Error in molecule viewer app: {str(e)}")
        st.error(f"Error displaying molecule viewer: {str(e)}")