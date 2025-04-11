import os
import logging
import json
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any, Union
import pymongo
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from bson.objectid import ObjectId

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class VisualizationService:
    def __init__(self, mongo_uri: str, mongo_db_name: str, plot_width: int = 900, plot_height: int = 600):
        """
        Initialize the VisualizationService.
        
        Args:
            mongo_uri: MongoDB connection URI
            mongo_db_name: MongoDB database name
            plot_width: Default plot width in pixels
            plot_height: Default plot height in pixels
        """
        self.mongo_uri = mongo_uri
        self.mongo_db_name = mongo_db_name
        self.plot_width = plot_width
        self.plot_height = plot_height
        self.mongo_client = None
        self.mongo_db = None
        
    def connect_to_mongo(self):
        """Connect to MongoDB."""
        try:
            if self.mongo_client is None:
                self.mongo_client = pymongo.MongoClient(self.mongo_uri)
                self.mongo_db = self.mongo_client[self.mongo_db_name]
                logger.info("Connected to MongoDB")
        except Exception as e:
            logger.error(f"Error connecting to MongoDB: {str(e)}")
            raise
            
    def close_connections(self):
        """Close MongoDB connection."""
        if self.mongo_client:
            self.mongo_client.close()
            self.mongo_client = None
            self.mongo_db = None
            logger.info("MongoDB connection closed")
            
    def get_visualization_data(self, compound_id: str) -> Optional[Dict[str, Any]]:
        """
        Get visualization data for a compound.
        
        Args:
            compound_id: The ID of the compound
            
        Returns:
            Optional[Dict[str, Any]]: Visualization data from MongoDB
        """
        try:
            self.connect_to_mongo()
                
            collection = self.mongo_db.get_collection("analysis_results")
            result = collection.find_one({"compound_id": compound_id})
            
            if result:
                return result
            return None
            
        except Exception as e:
            logger.error(f"Error retrieving visualization data: {str(e)}")
            return None
            
    def extract_plot_data(self, data: Dict[str, Any], x_field: str, y_field: str, color_field: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Extract data for plotting from raw analysis results.
        
        Args:
            data: The raw analysis data
            x_field: Field name for x-axis
            y_field: Field name for y-axis
            color_field: Optional field name for color coding
            
        Returns:
            List[Dict[str, Any]]: Data prepared for plotting
        """
        plot_data = []
        
        try:
            # Access the similar compounds list
            similar_compounds = data.get("results", {}).get("similar_compounds", [])
            
            for compound in similar_compounds:
                item = {}
                
                # Handle nested fields with dot notation
                if "." in x_field:
                    parts = x_field.split(".")
                    x_value = compound
                    for part in parts:
                        if isinstance(x_value, dict) and part in x_value:
                            x_value = x_value[part]
                        else:
                            x_value = None
                            break
                    item[x_field] = x_value
                else:
                    item[x_field] = compound.get(x_field)
                
                # Same for y_field
                if "." in y_field:
                    parts = y_field.split(".")
                    y_value = compound
                    for part in parts:
                        if isinstance(y_value, dict) and part in y_value:
                            y_value = y_value[part]
                        else:
                            y_value = None
                            break
                    item[y_field] = y_value
                else:
                    item[y_field] = compound.get(y_field)
                
                # And for color_field if provided
                if color_field:
                    if "." in color_field:
                        parts = color_field.split(".")
                        color_value = compound
                        for part in parts:
                            if isinstance(color_value, dict) and part in color_value:
                                color_value = color_value[part]
                            else:
                                color_value = None
                                break
                        item[color_field] = color_value
                    else:
                        item[color_field] = compound.get(color_field)
                
                # Add ChEMBL ID for hover info
                item["ChEMBL ID"] = compound.get("molecule_chembl_id", "Unknown")
                
                # Only include the item if both x and y values are present
                if item[x_field] is not None and item[y_field] is not None:
                    plot_data.append(item)
            
            return plot_data
            
        except Exception as e:
            logger.error(f"Error extracting plot data: {str(e)}")
            return []
            
    def generate_scatter_plot(self, data: List[Dict[str, Any]], x_field: str, y_field: str, 
                             color_field: Optional[str] = None, title: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Generate a scatter plot.
        
        Args:
            data: List of data points
            x_field: Field name for x-axis
            y_field: Field name for y-axis
            color_field: Optional field name for color coding
            title: Optional plot title
            
        Returns:
            Optional[Dict[str, Any]]: Plotly figure as JSON
        """
        try:
            # Convert to DataFrame for easier handling with Plotly Express
            df = pd.DataFrame(data)
            
            if df.empty:
                logger.warning("No data available for scatter plot")
                return None
            
            # Create the plot
            if color_field and color_field in df.columns:
                fig = px.scatter(
                    df,
                    x=x_field,
                    y=y_field,
                    color=color_field,
                    hover_name="ChEMBL ID",
                    title=title or f"{y_field} vs {x_field}",
                    width=self.plot_width,
                    height=self.plot_height
                )
            else:
                fig = px.scatter(
                    df,
                    x=x_field,
                    y=y_field,
                    hover_name="ChEMBL ID",
                    title=title or f"{y_field} vs {x_field}",
                    width=self.plot_width,
                    height=self.plot_height
                )
            
            # Update layout for better appearance
            fig.update_layout(
                template="plotly_white",
                xaxis_title=x_field,
                yaxis_title=y_field,
                legend_title=color_field if color_field else None,
                margin=dict(l=50, r=50, t=50, b=50)
            )
            
            # Convert to JSON
            return json.loads(fig.to_json())
            
        except Exception as e:
            logger.error(f"Error generating scatter plot: {str(e)}")
            return None
            
    def generate_efficiency_plots(self, compound_id: str) -> Optional[Dict[str, Any]]:
        """
        Generate efficiency index plots (SEI vs BEI, NSEI vs nBEI).
        
        Args:
            compound_id: The ID of the compound
            
        Returns:
            Optional[Dict[str, Any]]: Dictionary containing plot data
        """
        try:
            # Get data
            data = self.get_visualization_data(compound_id)
            if not data:
                logger.warning(f"No data found for compound {compound_id}")
                return None
            
            # Extract data for SEI vs BEI plot
            sei_bei_data = self.extract_plot_data(
                data=data,
                x_field="metrics.sei",
                y_field="metrics.bei",
                color_field="molecule_chembl_id"
            )
            
            # Extract data for NSEI vs nBEI plot
            nsei_nbei_data = self.extract_plot_data(
                data=data,
                x_field="metrics.nsei",
                y_field="metrics.nbei",
                color_field="molecule_chembl_id"
            )
            
            # Generate plots
            sei_bei_plot = None
            nsei_nbei_plot = None
            
            if sei_bei_data:
                sei_bei_plot = self.generate_scatter_plot(
                    data=sei_bei_data,
                    x_field="metrics.sei",
                    y_field="metrics.bei",
                    color_field="molecule_chembl_id",
                    title="Surface Efficiency Index (SEI) vs Binding Efficiency Index (BEI)"
                )
            
            if nsei_nbei_data:
                nsei_nbei_plot = self.generate_scatter_plot(
                    data=nsei_nbei_data,
                    x_field="metrics.nsei",
                    y_field="metrics.nbei",
                    color_field="molecule_chembl_id",
                    title="Normalized SEI vs Normalized BEI"
                )
            
            # Return plots
            return {
                "sei_bei_plot": sei_bei_plot,
                "nsei_nbei_plot": nsei_nbei_plot
            }
            
        except Exception as e:
            logger.error(f"Error generating efficiency plots: {str(e)}")
            return None
            
    def generate_activity_plot(self, compound_id: str) -> Optional[Dict[str, Any]]:
        """
        Generate activity distribution plot.
        
        Args:
            compound_id: The ID of the compound
            
        Returns:
            Optional[Dict[str, Any]]: Plotly figure as JSON
        """
        try:
            # Get data
            data = self.get_visualization_data(compound_id)
            if not data:
                logger.warning(f"No data found for compound {compound_id}")
                return None
            
            # Extract activities
            activities = []
            for compound in data.get("results", {}).get("similar_compounds", []):
                chembl_id = compound.get("molecule_chembl_id", "Unknown")
                for activity in compound.get("activities", []):
                    activities.append({
                        "ChEMBL ID": chembl_id,
                        "Activity Type": activity.get("type", "Unknown"),
                        "Value (nM)": activity.get("value")
                    })
            
            if not activities:
                logger.warning(f"No activity data found for compound {compound_id}")
                return None
            
            # Convert to DataFrame
            df = pd.DataFrame(activities)
            
            # Create box plot by activity type
            fig = px.box(
                df,
                x="Activity Type",
                y="Value (nM)",
                color="Activity Type",
                points="all",
                hover_name="ChEMBL ID",
                title="Activity Distribution by Type",
                width=self.plot_width,
                height=self.plot_height
            )
            
            # Use log scale for y-axis (typical for activity values)
            fig.update_yaxes(type="log")
            
            # Update layout
            fig.update_layout(
                template="plotly_white",
                xaxis_title="Activity Type",
                yaxis_title="Activity (nM, log scale)",
                showlegend=False,
                boxmode="group",
                margin=dict(l=50, r=50, t=50, b=50)
            )
            
            # Convert to JSON
            return json.loads(fig.to_json())
            
        except Exception as e:
            logger.error(f"Error generating activity plot: {str(e)}")
            return None