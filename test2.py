#!/usr/bin/env python3
import requests
import sys
import csv
from typing import Dict, List, Optional

class CompoundExporter:
    def __init__(self, api_gateway_url: str = "http://localhost:8000"):
        """
        Initialize the Compound Exporter.
        
        Args:
            api_gateway_url: Base URL for the API Gateway
        """
        self.base_url = api_gateway_url
        self.token = None
    
    def login(self, email: Optional[str] = None, password: Optional[str] = None):
        """
        Authenticate and obtain JWT token.
        
        Args:
            email: User email (optional)
            password: User password (optional)
        
        Returns:
            bool: True if login successful, False otherwise
        """
        # Default test user credentials
        default_email = "test@example.com"
        default_password = "testpassword"
        
        # Use provided credentials or fall back to defaults
        login_email = email or default_email
        login_password = password or default_password
        
        try:
            response = requests.post(
                f"{self.base_url}/auth/login", 
                json={"email": login_email, "password": login_password}
            )
            
            if response.status_code == 200:
                self.token = response.json().get('token')
                return True
            else:
                print(f"Login failed: {response.json().get('error', 'Unknown error')}")
                
                # If default credentials fail, try alternatives
                if login_email == default_email and login_password == default_password:
                    print("Attempting alternative test user credentials...")
                    try:
                        response = requests.post(
                            f"{self.base_url}/auth/login", 
                            json={"email": "test_user@example.com", "password": "test_password"}
                        )
                        
                        if response.status_code == 200:
                            self.token = response.json().get('token')
                            return True
                    except Exception as alt_e:
                        print(f"Alternative login attempt failed: {alt_e}")
                
                return False
        except Exception as e:
            print(f"Login error: {e}")
            return False
    
    def list_user_compounds(self) -> List[Dict]:
        """
        List compounds for the logged-in user.
        
        Returns:
            List of compounds owned by the user
        """
        if not self.token:
            print("Please login first.")
            return []
        
        try:
            response = requests.get(
                f"{self.base_url}/users/test_user/compounds",
                headers={"Authorization": f"Bearer {self.token}"}
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Failed to retrieve compounds: {response.json().get('error', 'Unknown error')}")
                return []
        except Exception as e:
            print(f"Error retrieving compounds: {e}")
            return []
    
    def get_compound_details(self, compound_id: str) -> Optional[Dict]:
        """
        Get detailed information for a specific compound.
        
        Args:
            compound_id: ID of the compound
        
        Returns:
            Compound details or None if retrieval fails
        """
        if not self.token:
            print("Please login first.")
            return None
        
        try:
            response = requests.get(
                f"{self.base_url}/compounds/{compound_id}",
                headers={"Authorization": f"Bearer {self.token}"}
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Failed to retrieve compound details: {response.json().get('error', 'Unknown error')}")
                return None
        except Exception as e:
            print(f"Error retrieving compound details: {e}")
            return None
    
    def get_compound_activities(self, compound_id: str) -> Optional[Dict]:
        """
        Get analysis results for a compound.
        
        Args:
            compound_id: ID of the compound
        
        Returns:
            Analysis results or None if retrieval fails
        """
        if not self.token:
            print("Please login first.")
            return None
        
        try:
            response = requests.get(
                f"{self.base_url}/analysis/{compound_id}/results",
                headers={"Authorization": f"Bearer {self.token}"}
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Failed to retrieve compound activities: {response.json().get('error', 'Unknown error')}")
                return None
        except Exception as e:
            print(f"Error retrieving compound activities: {e}")
            return None
    
    def export_compound_to_csv(self, compound_id: str, output_filename: Optional[str] = None):
        """
        Export compound details and activities to a CSV file.
        
        Args:
            compound_id: ID of the compound to export
            output_filename: Optional custom filename. If not provided, uses compound name.
        """
        # Get compound details
        compound_details = self.get_compound_details(compound_id)
        if not compound_details:
            print("Failed to retrieve compound details.")
            return
        
        # Get compound activities
        activities_data = self.get_compound_activities(compound_id)
        if not activities_data:
            print("Failed to retrieve compound activities.")
            return
        
        # Prepare filename
        compound_name = compound_details.get('name', 'compound')
        filename = output_filename or f"{compound_name}_export.csv"
        
        try:
            with open(filename, 'w', newline='') as csvfile:
                # Compound details header and data
                csvwriter = csv.writer(csvfile)
                csvwriter.writerow(["Compound Details"])
                for key, value in compound_details.items():
                    csvwriter.writerow([key, value])
                
                # Separator
                csvwriter.writerow([])
                
                # Activities header
                csvwriter.writerow(["Compound Activities"])
                csvwriter.writerow([
                    "Target ID", 
                    "Activity Type", 
                    "Relation", 
                    "Value", 
                    "Units", 
                    "SEI", 
                    "BEI", 
                    "NSEI", 
                    "NBEI", 
                    "p-Activity"
                ])
                
                # Write activities
                activities = activities_data.get('results', {}).get('activities', [])
                for activity in activities:
                    metrics = activity.get('metrics', {})
                    csvwriter.writerow([
                        activity.get('target_id', 'N/A'),
                        activity.get('activity_type', 'N/A'),
                        activity.get('relation', 'N/A'),
                        activity.get('value', 'N/A'),
                        activity.get('units', 'N/A'),
                        metrics.get('sei', 'N/A'),
                        metrics.get('bei', 'N/A'),
                        metrics.get('nsei', 'N/A'),
                        metrics.get('nbei', 'N/A'),
                        metrics.get('pActivity', 'N/A')
                    ])
                
                print(f"Exported compound data to {filename}")
        except Exception as e:
            print(f"Error exporting to CSV: {e}")
    
    def interactive_export(self):
        """
        Interactive export process for users.
        """
        # Login with test credentials
        if not self.login("test@example.com", "testpassword"):
            print("Login failed. Exiting.")
            return
        
        # List user compounds
        compounds = self.list_user_compounds()
        
        if not compounds:
            print("No compounds found.")
            return
        
        # Display compounds
        print("\nYour Compounds:")
        for i, compound in enumerate(compounds, 1):
            print(f"{i}. {compound.get('name', 'Unnamed Compound')} (ID: {compound['id']})")
        
        # Prompt for compound selection
        while True:
            try:
                selection = input("\nEnter the number of the compound you want to export (or 'q' to quit): ")
                
                if selection.lower() == 'q':
                    break
                
                index = int(selection) - 1
                if 0 <= index < len(compounds):
                    compound_id = compounds[index]['id']
                    output_filename = input("Enter output filename (optional, press Enter for default): ")
                    
                    if output_filename:
                        self.export_compound_to_csv(compound_id, output_filename)
                    else:
                        self.export_compound_to_csv(compound_id)
                else:
                    print("Invalid selection. Please try again.")
            
            except ValueError:
                print("Please enter a valid number or 'q'.")

def main():
    exporter = CompoundExporter()
    exporter.interactive_export()

if __name__ == "__main__":
    main()