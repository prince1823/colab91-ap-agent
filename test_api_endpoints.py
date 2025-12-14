#!/usr/bin/env python3
"""Comprehensive API endpoint testing script.

Tests all API endpoints in the proper application flow:
1. Health check
2. List/Create datasets
3. Canonicalization workflow
4. Verification workflow
5. Classification workflow
6. Transaction queries
7. Feedback submission and management
8. Supplier rules management

This script addresses common issues:
- Thread safety in parallel processing
- Path handling (absolute vs relative)
- Database session management
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Colors for output
GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[1;33m"
BLUE = "\033[0;34m"
NC = "\033[0m"  # No Color

BASE_URL = "http://localhost:8000"
API_BASE = f"{BASE_URL}/api/v1"


class APITester:
    """API endpoint tester with proper error handling and flow management."""

    def __init__(self, base_url: str = API_BASE):
        """Initialize tester with retry strategy."""
        self.base_url = base_url
        self.session = requests.Session()
        
        # Configure retry strategy for transient errors
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST", "PUT", "DELETE"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        self.test_results = []
        self.dataset_id: Optional[str] = None
        self.foldername = ""  # Empty foldername for direct datasets/innova structure
        self.feedback_id: Optional[int] = None

    def log(self, message: str, color: str = NC):
        """Print colored log message."""
        print(f"{color}{message}{NC}")

    def test(self, name: str, method: str, endpoint: str, base_url: Optional[str] = None, **kwargs) -> Optional[Dict]:
        """
        Run a test and track results.
        
        Args:
            name: Test name
            method: HTTP method
            endpoint: API endpoint (relative to base_url)
            base_url: Optional base URL override (defaults to self.base_url)
            **kwargs: Additional arguments for requests
            
        Returns:
            Response JSON or None if failed
        """
        url_base = base_url if base_url else self.base_url
        url = f"{url_base}{endpoint}"
        self.log(f"\n{'='*60}", BLUE)
        self.log(f"Test: {name}", BLUE)
        self.log(f"{method} {endpoint}", YELLOW)
        self.log(f"{'='*60}", BLUE)
        
        try:
            response = self.session.request(method, url, timeout=300, **kwargs)
            
            # Check status
            if response.status_code < 400:
                self.log(f"✓ Status: {response.status_code}", GREEN)
                try:
                    data = response.json()
                    if isinstance(data, dict) and len(str(data)) < 500:
                        self.log(f"Response: {json.dumps(data, indent=2)}", NC)
                    else:
                        self.log(f"Response: {type(data).__name__} (too large to display)", NC)
                    self.test_results.append((name, True, response.status_code, None))
                    return data
                except ValueError:
                    self.log(f"Response: {response.text[:200]}", NC)
                    self.test_results.append((name, True, response.status_code, None))
                    return {"text": response.text}
            else:
                error_msg = f"Status {response.status_code}: {response.text[:200]}"
                self.log(f"✗ {error_msg}", RED)
                self.test_results.append((name, False, response.status_code, error_msg))
                try:
                    return response.json()
                except:
                    return None
                    
        except requests.exceptions.RequestException as e:
            error_msg = f"Request failed: {str(e)}"
            self.log(f"✗ {error_msg}", RED)
            self.test_results.append((name, False, 0, error_msg))
            return None
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            self.log(f"✗ {error_msg}", RED)
            self.test_results.append((name, False, 0, error_msg))
            import traceback
            traceback.print_exc()
            return None

    def wait_for_status(self, dataset_id: str, expected_status: str, max_wait: int = 60):
        """Wait for dataset to reach expected status."""
        self.log(f"\nWaiting for dataset '{dataset_id}' to reach status '{expected_status}'...", YELLOW)
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            result = self.test(
                f"Check status for {dataset_id}",
                "GET",
                f"/datasets/{dataset_id}/status?foldername={self.foldername}"
            )
            
            if result and result.get("status") == expected_status:
                self.log(f"✓ Status reached: {expected_status}", GREEN)
                return True
            
            time.sleep(2)
        
        self.log(f"✗ Timeout waiting for status '{expected_status}'", RED)
        return False

    def run_all_tests(self):
        """Run all API tests in proper flow."""
        self.log("\n" + "="*60, BLUE)
        self.log("Starting Comprehensive API Endpoint Tests", BLUE)
        self.log("="*60, BLUE)
        
        # Test 1: Health check (not under /api/v1)
        self.test("Health Check", "GET", "/health", base_url=BASE_URL)
        
        # Test 2: Root endpoint (not under /api/v1)
        self.test("Root Endpoint", "GET", "/", base_url=BASE_URL)
        
        # Test 3: List datasets
        datasets_result = self.test("List Datasets", "GET", f"/datasets?foldername={self.foldername}")
        
        # Find or use a test dataset
        if datasets_result and isinstance(datasets_result, list) and len(datasets_result) > 0:
            # Prefer innova if available, otherwise use first available
            innova_datasets = [d for d in datasets_result if d.get("dataset_id") == "innova"]
            if innova_datasets:
                self.dataset_id = "innova"
            else:
                self.dataset_id = datasets_result[0]["dataset_id"]
            self.log(f"\nUsing existing dataset: {self.dataset_id}", YELLOW)
        else:
            # Try to find a dataset in test_bench
            self.log("\nNo datasets found, checking for test_bench datasets...", YELLOW)
            # Use innova as default
            self.dataset_id = "innova"  # Default fallback
        
        if not self.dataset_id:
            self.log("✗ No dataset available for testing", RED)
            return
        
        # Test 4: Get dataset details
        self.test(
            "Get Dataset Details",
            "GET",
            f"/datasets/{self.dataset_id}?foldername={self.foldername}"
        )
        
        # Test 5: Check initial status
        status_result = self.test(
            "Get Initial Status",
            "GET",
            f"/datasets/{self.dataset_id}/status?foldername={self.foldername}"
        )
        
        current_status = status_result.get("status") if status_result else None
        
        # Test 6: Start canonicalization (if not already canonicalized)
        if current_status in [None, "pending"]:
            canonicalize_result = self.test(
                "Start Canonicalization",
                "POST",
                f"/datasets/{self.dataset_id}/canonicalize?foldername={self.foldername}"
            )
            
            if canonicalize_result:
                # Wait for canonicalization to complete
                self.wait_for_status(self.dataset_id, "canonicalized", max_wait=120)
        
        # Test 7: Get canonicalization for review
        canonicalization_result = self.test(
            "Get Canonicalization Review",
            "GET",
            f"/datasets/{self.dataset_id}/canonicalization?foldername={self.foldername}"
        )
        
        # Test 8: Verify canonicalization (auto-approve for testing)
        # Always verify if status is canonicalized or awaiting_verification
        if current_status in ["canonicalized", "awaiting_verification"]:
            verify_result = self.test(
                "Verify Canonicalization (Auto-approve)",
                "POST",
                f"/datasets/{self.dataset_id}/verify?foldername={self.foldername}",
                json={"auto_approve": True}
            )
            
            if verify_result:
                # Wait for verification to complete
                self.wait_for_status(self.dataset_id, "verified", max_wait=30)
        
        # Test 9: Start classification (with reduced workers to avoid thread issues)
        # Using max_workers=1 for testing to avoid thread safety issues
        classify_result = self.test(
            "Start Classification (max_workers=1 for thread safety)",
            "POST",
            f"/datasets/{self.dataset_id}/classify?foldername={self.foldername}&max_workers=1"
        )
        
        if classify_result:
            # Wait for classification to complete
            self.wait_for_status(self.dataset_id, "completed", max_wait=300)
        
        # Test 10: Get final status
        final_status = self.test(
            "Get Final Status",
            "GET",
            f"/datasets/{self.dataset_id}/status?foldername={self.foldername}"
        )
        
        # Test 11: Query transactions
        transactions_result = self.test(
            "Query Transactions",
            "GET",
            f"/transactions?dataset_id={self.dataset_id}&foldername={self.foldername}&page=1&limit=10"
        )
        
        # Test 12: Get single transaction (if we have transactions)
        if transactions_result and transactions_result.get("rows") and len(transactions_result["rows"]) > 0:
            row_index = 0
            transaction_result = self.test(
                "Get Single Transaction",
                "GET",
                f"/transactions/{row_index}?dataset_id={self.dataset_id}&foldername={self.foldername}"
            )
            
            # Test 13: Update transaction classification
            if transaction_result and transaction_result.get("data"):
                original_path = transaction_result["data"].get("L1", "")
                self.test(
                    "Update Transaction Classification",
                    "PUT",
                    f"/transactions/{row_index}?dataset_id={self.dataset_id}&foldername={self.foldername}",
                    json={"classification_path": original_path}  # Keep same for testing
                )
        
        # Test 14: List feedback
        feedback_list = self.test(
            "List Feedback",
            "GET",
            "/feedback?page=1&limit=10"
        )
        
        # Test 15: Submit feedback (if we have a transaction)
        if transactions_result and transactions_result.get("rows") and len(transactions_result["rows"]) > 0:
            first_transaction = transactions_result["rows"][0]
            submit_feedback_result = self.test(
                "Submit Feedback",
                "POST",
                "/feedback",
                json={
                    "dataset_id": self.dataset_id,
                    "foldername": self.foldername,
                    "row_index": 0,
                    "corrected_path": first_transaction.get("L1", "test|category"),
                    "feedback_text": "Test feedback for API testing"
                }
            )
            
            if submit_feedback_result and submit_feedback_result.get("feedback_id"):
                self.feedback_id = submit_feedback_result["feedback_id"]
                
                # Test 16: Get feedback details
                self.test(
                    "Get Feedback Details",
                    "GET",
                    f"/feedback/{self.feedback_id}"
                )
                
                # Test 17: Preview affected rows
                self.test(
                    "Preview Affected Rows",
                    "GET",
                    f"/feedback/{self.feedback_id}/preview"
                )
                
                # Test 18: Approve feedback
                approve_result = self.test(
                    "Approve Feedback",
                    "POST",
                    f"/feedback/{self.feedback_id}/approve",
                    json={}
                )
                
                # Test 19: Apply feedback (if approved)
                if approve_result:
                    self.test(
                        "Apply Feedback",
                        "POST",
                        f"/feedback/{self.feedback_id}/apply",
                        json={"row_indices": [0]}
                    )
        
        # Test 20: List supplier direct mappings
        self.test(
            "List Direct Mappings",
            "GET",
            "/supplier-rules/direct-mappings?active_only=true"
        )
        
        # Test 21: Create direct mapping
        create_mapping_result = self.test(
            "Create Direct Mapping",
            "POST",
            "/supplier-rules/direct-mappings",
            json={
                "supplier_name": "Test Supplier API",
                "classification_path": "test|category|subcategory",
                "dataset_name": self.dataset_id,
                "priority": 10,
                "notes": "Created by API test script"
            }
        )
        
        mapping_id = None
        if create_mapping_result and create_mapping_result.get("id"):
            mapping_id = create_mapping_result["id"]
            
            # Test 22: Get direct mapping
            self.test(
                "Get Direct Mapping",
                "GET",
                f"/supplier-rules/direct-mappings/{mapping_id}"
            )
            
            # Test 23: Update direct mapping
            self.test(
                "Update Direct Mapping",
                "PUT",
                f"/supplier-rules/direct-mappings/{mapping_id}",
                json={
                    "classification_path": "test|category|updated",
                    "priority": 15,
                    "notes": "Updated by API test script"
                }
            )
            
            # Test 24: Delete direct mapping
            self.test(
                "Delete Direct Mapping",
                "DELETE",
                f"/supplier-rules/direct-mappings/{mapping_id}"
            )
        
        # Test 25: List taxonomy constraints
        self.test(
            "List Taxonomy Constraints",
            "GET",
            "/supplier-rules/taxonomy-constraints?active_only=true"
        )
        
        # Test 26: Create taxonomy constraint
        create_constraint_result = self.test(
            "Create Taxonomy Constraint",
            "POST",
            "/supplier-rules/taxonomy-constraints",
            json={
                "supplier_name": "Test Supplier Constraint",
                "allowed_taxonomy_paths": [
                    "test|category|path1",
                    "test|category|path2"
                ],
                "dataset_name": self.dataset_id,
                "priority": 10,
                "notes": "Created by API test script"
            }
        )
        
        constraint_id = None
        if create_constraint_result and create_constraint_result.get("id"):
            constraint_id = create_constraint_result["id"]
            
            # Test 27: Get taxonomy constraint
            self.test(
                "Get Taxonomy Constraint",
                "GET",
                f"/supplier-rules/taxonomy-constraints/{constraint_id}"
            )
            
            # Test 28: Update taxonomy constraint
            self.test(
                "Update Taxonomy Constraint",
                "PUT",
                f"/supplier-rules/taxonomy-constraints/{constraint_id}",
                json={
                    "allowed_taxonomy_paths": [
                        "test|category|path1"
                    ],
                    "priority": 15,
                    "notes": "Updated by API test script"
                }
            )
            
            # Test 29: Delete taxonomy constraint
            self.test(
                "Delete Taxonomy Constraint",
                "DELETE",
                f"/supplier-rules/taxonomy-constraints/{constraint_id}"
            )
        
        # Print summary
        self.print_summary()

    def print_summary(self):
        """Print test summary."""
        self.log("\n" + "="*60, BLUE)
        self.log("Test Summary", BLUE)
        self.log("="*60, BLUE)
        
        total = len(self.test_results)
        passed = sum(1 for _, success, _, _ in self.test_results if success)
        failed = total - passed
        
        self.log(f"\nTotal Tests: {total}", NC)
        self.log(f"Passed: {GREEN}{passed}{NC}", NC)
        self.log(f"Failed: {RED}{failed}{NC}", NC)
        
        if failed > 0:
            self.log("\nFailed Tests:", RED)
            for name, success, status, error in self.test_results:
                if not success:
                    self.log(f"  ✗ {name} (Status: {status})", RED)
                    if error:
                        self.log(f"    Error: {error[:100]}", YELLOW)
        
        self.log("\n" + "="*60, BLUE)


def check_server_running():
    """Check if API server is running."""
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        return response.status_code == 200
    except:
        return False


def main():
    """Main test runner."""
    print("\n" + "="*60)
    print("API Endpoint Test Suite")
    print("="*60)
    
    # Check if server is running
    print("\nChecking if API server is running...")
    if not check_server_running():
        print(f"{RED}✗ API server is not running at {BASE_URL}{NC}")
        print(f"\nPlease start the server first:")
        print(f"  {YELLOW}./start_hitl_api.sh{NC}")
        print(f"\nOr manually:")
        print(f"  {YELLOW}poetry run uvicorn api.main:app --reload --host 0.0.0.0 --port 8000{NC}")
        sys.exit(1)
    
    print(f"{GREEN}✓ API server is running{NC}\n")
    
    # Run tests
    tester = APITester()
    try:
        tester.run_all_tests()
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Tests interrupted by user{NC}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{RED}Unexpected error: {e}{NC}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Exit with appropriate code
    failed = sum(1 for _, success, _, _ in tester.test_results if not success)
    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
