#!/usr/bin/env python3
import requests
import json
import time
import sys
from pprint import pprint

# Configuration
API_GATEWAY = "http://localhost:8000"
TEST_USER_ID = "test_user"
TEST_SMILES = "O=c1c(O)c(-c2ccc(O)c(O)c2)oc2cc(O)cc(O)c12"  # Quercetin
TEST_NAME = "Quercetin"

# Helper function for API calls
def api_call(method, endpoint, data=None, token=None):
    url = f"{API_GATEWAY}{endpoint}"
    headers = {'Content-Type': 'application/json'}
    
    if token:
        headers['Authorization'] = f"Bearer {token}"
    
    if method == 'GET':
        response = requests.get(url, headers=headers)
    elif method == 'POST':
        response = requests.post(url, headers=headers, data=json.dumps(data))
    elif method == 'PUT':
        response = requests.put(url, headers=headers, data=json.dumps(data))
    elif method == 'DELETE':
        response = requests.delete(url, headers=headers)
    else:
        raise ValueError(f"Unsupported method: {method}")
    
    return response

def run_tests():
    print("Testing IMPULATOR API Gateway...")
    
    # Test 1: Health check
    print("\n1. Testing health check endpoint...")
    response = api_call('GET', '/health')
    print(f"Status code: {response.status_code}")
    print(f"Response: {response.json()}")
    
    # Test 2: User registration
    print("\n2. Testing user registration...")
    user_data = {
        "username": f"testuser_{int(time.time())}",
        "email": f"test_{int(time.time())}@example.com",
        "password": "testpassword"
    }
    response = api_call('POST', '/auth/register', user_data)
    print(f"Status code: {response.status_code}")
    print(f"Response: {response.json()}")
    
    # Test 3: User login
    print("\n3. Testing user login...")
    login_data = {
        "email": user_data["email"],
        "password": user_data["password"]
    }
    response = api_call('POST', '/auth/login', login_data)
    print(f"Status code: {response.status_code}")
    result = response.json()
    print(f"Response: {result}")
    
    if 'token' not in result:
        print("ERROR: Login failed, no token received")
        return
    
    token = result['token']
    
    # Test 4: Create a compound
    print("\n4. Testing compound creation...")
    compound_data = {
        "name": TEST_NAME,
        "smiles": TEST_SMILES,
        "user_id": TEST_USER_ID,
        "similarity_threshold": 80
    }
    response = api_call('POST', '/compounds', compound_data, token)
    print(f"Status code: {response.status_code}")
    result = response.json()
    print(f"Response: {result}")
    
    if 'id' not in result:
        print("ERROR: Compound creation failed, no ID received")
        return
    
    compound_id = result['id']
    
    # Test 5: Get compound details
    print(f"\n5. Testing get compound details for {compound_id}...")
    
    # Wait a bit for the compound to be processed
    print("Waiting for compound to be processed...")
    time.sleep(5)
    
    response = api_call('GET', f'/compounds/{compound_id}', token=token)
    print(f"Status code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    
    # Test 6: Get job status
    print("\n6. Testing job status retrieval...")
    
    # Extract job_id from compound response if available
    compound_details = response.json()
    job_id = compound_details.get('analysis_job_id')
    
    if not job_id:
        print("No job ID found, trying to find from user compounds...")
        response = api_call('GET', f'/users/{TEST_USER_ID}/compounds', token=token)
        compounds = response.json()
        for comp in compounds:
            if comp.get('id') == compound_id and 'job_id' in comp:
                job_id = comp.get('job_id')
                break
    
    if job_id:
        print(f"Found job ID: {job_id}")
        response = api_call('GET', f'/analysis/{job_id}', token=token)
        print(f"Status code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
    else:
        print("ERROR: No job ID found")
    
    # Test 7: Monitor job progress for a while
    if job_id:
        print("\n7. Monitoring job progress...")
        max_attempts = 30
        for i in range(max_attempts):
            response = api_call('GET', f'/analysis/{job_id}', token=token)
            job_status = response.json()
            status = job_status.get('status')
            progress = job_status.get('progress', 0)
            
            print(f"Job status: {status}, Progress: {progress:.1%}")
            
            if status == 'completed':
                print("Job completed successfully!")
                break
            elif status == 'failed':
                print("Job failed!")
                break
            
            if i < max_attempts - 1:
                print("Waiting 10 seconds before checking again...")
                time.sleep(10)
        
        # Test 8: Get analysis results
        print("\n8. Getting analysis results...")
        response = api_call('GET', f'/analysis/{compound_id}/results', token=token)
        print(f"Status code: {response.status_code}")
        if response.status_code == 200:
            # Print a summary instead of the full results which can be very large
            results = response.json()
            activities_count = len(results.get('results', {}).get('activities', []))
            print(f"Retrieved analysis results with {activities_count} activities")
        else:
            print(f"Response: {response.text}")
        
        # Test 9: Get visualizations
        print("\n9. Getting visualizations...")
        response = api_call('GET', f'/visualizations/{compound_id}/efficiency-plots', token=token)
        print(f"Efficiency plots status code: {response.status_code}")
        if response.status_code == 200:
            plot_keys = response.json().keys()
            print(f"Retrieved visualization plots: {', '.join(plot_keys)}")
        
        response = api_call('GET', f'/visualizations/{compound_id}/activity-plot', token=token)
        print(f"Activity plot status code: {response.status_code}")
        if response.status_code == 200:
            print("Retrieved activity plot data")
    
    print("\nTests completed!")

if __name__ == "__main__":
    run_tests()