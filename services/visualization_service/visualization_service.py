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

from config import Config

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
            
    def get_visualization_data(self, job_id: str, compound_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get visualization data for a job, optionally filtered by compound.
        
        Args:
            job_id: The ID of the job
            compound_id: Optional ID of the compound to filter by
            
        Returns:
            Optional[Dict[str, Any]]: Visualization data from MongoDB
        """
        try:
            self.connect_to_mongo()
                
            collection = self.mongo_db["analysis_results"]
            
            # If we're looking for a specific compound in a job
            if compound_id:
                # Check if it's the primary compound
                primary = collection.find_one({
                    "job_id": job_id,
                    "primary_compound.compound_id": compound_id
                })
                
                if primary:
                    result = {
                        "_id": str(primary["_id"]),
                        "job_id": job_id,
                        "compound_id": compound_id,
                        "results": primary["primary_compound"]["results"]
                    }
                    return result
                
                # Check if it's a similar compound
                similar = collection.find_one({
                    "job_id": job_id,
                    "similar_compounds.compound_id": compound_id
                })
                
                if similar:
                    # Find the specific similar compound
                    for comp in similar["similar_compounds"]:
                        if comp["compound_id"] == compound_id:
                            result = {
                                "_id": str(similar["_id"]),
                                "job_id": job_id,
                                "compound_id": compound_id,
                                "results": comp["results"]
                            }
                            return result
                
                logger.warning(f"No visualization data found for job {job_id}, compound {compound_id}")
                return None
            else:
                # Get the entire job document
                result = collection.find_one({"job_id": job_id})
                
                if result:
                    # Convert ObjectId to string for JSON serialization
                    result['_id'] = str(result['_id'])
                    logger.info(f"Retrieved visualization data for job {job_id}")
                    return result
                
                logger.warning(f"No visualization data found for job {job_id}")
                return None
                
        except Exception as e:
            logger.error(f"Error retrieving visualization data: {str(e)}")
            return None
                
    def extract_plot_data(self, result: Dict[str, Any], plot_type: str) -> List[Dict[str, Any]]:
        """
        Extract data for a specific plot type from analysis results.
        
        Args:
            result: Analysis results from MongoDB
            plot_type: Type of plot to extract data for
            
        Returns:
            List[Dict[str, Any]]: Data prepared for plotting
        """
        try:
            if not result or 'results' not in result:
                return []
                
            activities = result['results'].get('activities', [])
            plot_data = []
            
            # Process based on plot type
            if plot_type == 'efficiency_metrics':
                # Get efficiency metrics for each activity
                for activity in activities:
                    metrics = activity.get('metrics', {})
                    if metrics:
                        plot_data.append({
                            'target_id': activity.get('target_id', 'Unknown'),
                            'activity_type': activity.get('activity_type', 'Unknown'),
                            'value': activity.get('value', 0),
                            'sei': metrics.get('sei', 0),
                            'bei': metrics.get('bei', 0),
                            'nsei': metrics.get('nsei', 0),
                            'nbei': metrics.get('nbei', 0),
                            'pActivity': metrics.get('pActivity', 0)
                        })
            
            elif plot_type == 'activity':
                # Get activity data
                for activity in activities:
                    plot_data.append({
                        'target_id': activity.get('target_id', 'Unknown'),
                        'activity_type': activity.get('activity_type', 'Unknown'),
                        'value': activity.get('value', 0),
                        'units': activity.get('units', 'nM')
                    })
                    
            elif plot_type == 'sei_vs_bei':
                # Get SEI vs BEI data
                for activity in activities:
                    metrics = activity.get('metrics', {})
                    if metrics and metrics.get('sei', 0) > 0 and metrics.get('bei', 0) > 0:
                        plot_data.append({
                            'target_id': activity.get('target_id', 'Unknown'),
                            'activity_type': activity.get('activity_type', 'Unknown'),
                            'value': activity.get('value', 0),
                            'sei': metrics.get('sei', 0),
                            'bei': metrics.get('bei', 0)
                        })
            
            elif plot_type == 'nsei_vs_nbei':
                # Get NSEI vs nBEI data
                for activity in activities:
                    metrics = activity.get('metrics', {})
                    if metrics and metrics.get('nsei', 0) > 0 and metrics.get('nbei', 0) > 0:
                        plot_data.append({
                            'target_id': activity.get('target_id', 'Unknown'),
                            'activity_type': activity.get('activity_type', 'Unknown'),
                            'value': activity.get('value', 0),
                            'nsei': metrics.get('nsei', 0),
                            'nbei': metrics.get('nbei', 0)
                        })
            
            return plot_data
            
        except Exception as e:
            logger.error(f"Error extracting plot data: {str(e)}")
            return []
            
    def generate_efficiency_plots(self, job_id: str, compound_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Generate efficiency index plots (SEI vs BEI, NSEI vs nBEI).
        
        Args:
            compound_id: The ID of the compound
            
        Returns:
            Optional[Dict[str, Any]]: Dictionary containing plot data
        """
        try:
            # Get data
            data = self.get_visualization_data(job_id, compound_id)
            if not data:
                logger.warning(f"No data found for compound {compound_id}")
                return None
            
            # Extract data for SEI vs BEI plot
            sei_bei_data = self.extract_plot_data(data, 'sei_vs_bei')
            
            # Extract data for NSEI vs nBEI plot
            nsei_nbei_data = self.extract_plot_data(data, 'nsei_vs_nbei')
            
            # Generate plots
            sei_bei_plot = None
            nsei_nbei_plot = None
            
            if sei_bei_data:
                # Convert to pandas DataFrame
                df_sei_bei = pd.DataFrame(sei_bei_data)
                
                # Create SEI vs BEI scatter plot
                fig = px.scatter(
                    df_sei_bei,
                    x='sei',
                    y='bei',
                    color='activity_type',
                    hover_name='target_id',
                    hover_data=['value'],
                    title='Surface Efficiency Index (SEI) vs Binding Efficiency Index (BEI)',
                    width=self.plot_width,
                    height=self.plot_height
                )
                
                # Update layout
                fig.update_layout(
                    template='plotly_white',
                    xaxis_title='SEI',
                    yaxis_title='BEI',
                    legend_title='Activity Type'
                )
                
                # Convert to JSON
                sei_bei_plot = json.loads(fig.to_json())
            
            if nsei_nbei_data:
                # Convert to pandas DataFrame
                df_nsei_nbei = pd.DataFrame(nsei_nbei_data)
                
                # Create NSEI vs nBEI scatter plot
                fig = px.scatter(
                    df_nsei_nbei,
                    x='nsei',
                    y='nbei',
                    color='activity_type',
                    hover_name='target_id',
                    hover_data=['value'],
                    title='Normalized SEI vs Normalized BEI',
                    width=self.plot_width,
                    height=self.plot_height
                )
                
                # Update layout
                fig.update_layout(
                    template='plotly_white',
                    xaxis_title='NSEI',
                    yaxis_title='nBEI',
                    legend_title='Activity Type'
                )
                
                # Convert to JSON
                nsei_nbei_plot = json.loads(fig.to_json())
            
            # Return plots
            return {
                'sei_bei_plot': sei_bei_plot,
                'nsei_nbei_plot': nsei_nbei_plot
            }
            
        except Exception as e:
            logger.error(f"Error generating efficiency plots: {str(e)}")
            return None
            
    def generate_activity_plot(self, job_id: str, compound_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Generate activity distribution plot.
        
        Args:
            compound_id: The ID of the compound
            
        Returns:
            Optional[Dict[str, Any]]: Plotly figure as JSON
        """
        try:
            # Get data
            data = self.get_visualization_data(job_id, compound_id)
            if not data:
                logger.warning(f"No data found for compound {compound_id}")
                return None
            
            # Extract activity data
            activity_data = self.extract_plot_data(data, 'activity')
            
            if not activity_data:
                logger.warning(f"No activity data found for compound {compound_id}")
                return None
            
            # Convert to pandas DataFrame
            df = pd.DataFrame(activity_data)
            
            # Create activity box plot by activity type
            fig = px.box(
                df,
                x='activity_type',
                y='value',
                color='activity_type',
                points='all',
                hover_name='target_id',
                title='Activity Distribution by Type',
                width=self.plot_width,
                height=self.plot_height
            )
            
            # Use log scale for y-axis (typical for activity values)
            fig.update_yaxes(type="log")
            
            # Update layout
            fig.update_layout(
                template='plotly_white',
                xaxis_title='Activity Type',
                yaxis_title='Activity Value (nM, log scale)',
                showlegend=False
            )
            
            # Convert to JSON
            return json.loads(fig.to_json())
            
        except Exception as e:
            logger.error(f"Error generating activity plot: {str(e)}")
            return None
            
    def generate_custom_plot(self, compound_id: str, x_field: str, y_field: str, 
                           color_field: Optional[str] = None, title: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Generate a custom scatter plot.
        
        Args:
            compound_id: The ID of the compound
            x_field: Field name for x-axis
            y_field: Field name for y-axis
            color_field: Optional field name for color coding
            title: Optional plot title
            
        Returns:
            Optional[Dict[str, Any]]: Plotly figure as JSON
        """
        try:
            # Get data
            data = self.get_visualization_data(compound_id)
            if not data:
                logger.warning(f"No data found for compound {compound_id}")
                return None
            
            # Extract all plot data (efficiency metrics)
            plot_data = self.extract_plot_data(data, 'efficiency_metrics')
            
            if not plot_data:
                logger.warning(f"No plot data found for compound {compound_id}")
                return None
            
            # Check if required fields exist
            valid_fields = set(plot_data[0].keys())
            if x_field not in valid_fields or y_field not in valid_fields:
                logger.warning(f"Invalid fields: {x_field}, {y_field}. Valid fields are: {valid_fields}")
                return None
            
            if color_field and color_field not in valid_fields:
                logger.warning(f"Invalid color field: {color_field}. Valid fields are: {valid_fields}")
                color_field = None
                
            # Convert to pandas DataFrame
            df = pd.DataFrame(plot_data)
            
            # Create custom scatter plot
            if color_field:
                fig = px.scatter(
                    df,
                    x=x_field,
                    y=y_field,
                    color=color_field,
                    hover_name='target_id',
                    hover_data=['value'],
                    title=title or f"{y_field} vs {x_field}",
                    width=self.plot_width,
                    height=self.plot_height
                )
            else:
                fig = px.scatter(
                    df,
                    x=x_field,
                    y=y_field,
                    hover_name='target_id',
                    hover_data=['value'],
                    title=title or f"{y_field} vs {x_field}",
                    width=self.plot_width,
                    height=self.plot_height
                )
            
            # Update layout
            fig.update_layout(
                template='plotly_white',
                xaxis_title=x_field,
                yaxis_title=y_field,
                legend_title=color_field
            )
            
            # Convert to JSON
            return json.loads(fig.to_json())
            
        except Exception as e:
            logger.error(f"Error generating custom plot: {str(e)}")
            return None