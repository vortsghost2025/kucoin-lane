"""
Unit tests for CreatorTrackerAgent
"""
import json
import os
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, mock_open

import pytest

from src.intelligence.creator_tracker import CreatorTrackerAgent, CreatorProfile


class TestCreatorTrackerAgent:
    def test_initialization(self):
        """Test agent initializes with empty registry."""
        agent = CreatorTrackerAgent()
        assert agent.agent_name == "CreatorTrackerAgent"
        assert len(agent.creator_profiles) == 0
        assert agent.db_path.name == "creator_registry.json"

    def test_initialization_with_custom_path(self):
        """Test agent accepts custom DB path."""
        custom_path = "/tmp/custom_creators.json"
        agent = CreatorTrackerAgent({"creator_db_path": custom_path})
        assert agent.db_path == Path(custom_path)

    def test_load_registry_file_not_exists(self):
        """Test loading when registry file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "nonexistent.json"
            agent = CreatorTrackerAgent({"creator_db_path": str(db_path)})
            assert len(agent.creator_profiles) == 0

    def test_load_registry_success(self):
        """Test loading existing registry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "creator_registry.json"
            test_data = {
                "test_creator": {
                    "creator_id": "test_creator",
                    "type": "wallet",
                    "display_name": "Test Creator",
                    "first_seen": "2026-01-01T00:00:00Z",
                    "token_history": [],
                    "performance_metrics": {},
                    "social_links": {},
                    "reputation_score": 0.5,
                    "tags": []
                }
            }
            db_path.write_text(json.dumps(test_data))
            
            agent = CreatorTrackerAgent({"creator_db_path": str(db_path)})
            assert len(agent.creator_profiles) == 1
            assert "test_creator" in agent.creator_profiles
            profile = agent.creator_profiles["test_creator"]
            assert profile.display_name == "Test Creator"
            assert profile.reputation_score == 0.5

    def test_save_registry(self):
        """Test saving registry to disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "creator_registry.json"
            agent = CreatorTrackerAgent({"creator_db_path": str(db_path)})
            
            # Add a profile
            profile = CreatorProfile(
                creator_id="test_creator",
                type="wallet",
                display_name="Test Creator",
                first_seen="2026-01-01T00:00:00Z"
            )
            agent.creator_profiles["test_creator"] = profile
            
            # Save and verify
            agent._save_registry()
            assert db_path.exists()
            
            # Load back and verify
            with open(db_path) as f:
                data = json.load(f)
            assert "test_creator" in data
            assert data["test_creator"]["creator_id"] == "test_creator"

    def test_execute_new_creator(self):
        """Test detecting a new creator."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "creator_registry.json"
            agent = CreatorTrackerAgent({"creator_db_path": str(db_path)})
            
            input_data = {
                "dex_signals": [{
                    "pair": "SOL/USDC",
                    "deployer": "new_wallet_123",
                    "composite_score": 0.8,
                    "signal": "BUY",
                    "scan_time": "2026-06-05T12:00:00Z"
                }]
            }
            
            result = agent.execute(input_data)
            
            assert result["success"] is True
            assert len(result["data"]["new_creators"]) == 1
            assert len(agent.creator_profiles) == 1
            
            profile = list(agent.creator_profiles.values())[0]
            assert profile.creator_id == "new_wallet_123"
            assert profile.reputation_score == 0.1  # Initial score
            assert len(profile.token_history) == 1

    def test_execute_existing_creator(self):
        """Test updating existing creator profile."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "creator_registry.json"
            agent = CreatorTrackerAgent({"creator_db_path": str(db_path)})
            
            # Pre-populate with a creator
            profile = CreatorProfile(
                creator_id="existing_wallet",
                type="wallet",
                display_name="Existing Wallet",
                first_seen="2026-01-01T00:00:00Z",
                token_history=[{
                    "token": "OLD",
                    "timestamp": "2026-01-01T00:00:00Z",
                    "composite_score": 0.5,
                    "signal": "NEUTRAL"
                }],
                performance_metrics={"avg_score": 0.5},
                reputation_score=0.5
            )
            agent.creator_profiles["existing_wallet"] = profile
            
            # Execute with new signal from same creator
            input_data = {
                "dex_signals": [{
                    "pair": "NEW/USDC",
                    "deployer": "existing_wallet",
                    "composite_score": 0.9,
                    "signal": "STRONG_BUY",
                    "scan_time": "2026-06-05T12:00:00Z"
                }]
            }
            
            result = agent.execute(input_data)
            
            assert result["success"] is True
            assert len(agent.creator_profiles) == 1
            assert len(agent.creator_profiles["existing_wallet"].token_history) == 2
            
            # Check updated reputation
            updated_profile = agent.creator_profiles["existing_wallet"]
            assert updated_profile.performance_metrics["avg_score"] == 0.7  # (0.5 + 0.9) / 2
            assert updated_profile.reputation_score > 0.5  # Should increase

    def test_get_alpha_creators(self):
        """Test filtering for high-reputation creators."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "creator_registry.json"
            agent = CreatorTrackerAgent({"creator_db_path": str(db_path)})
            
            # Create mix of profiles
            low_rep = CreatorProfile(
                creator_id="low", type="wallet", display_name="Low",
                first_seen="2026-01-01T00:00:00Z", reputation_score=0.2
            )
            high_rep = CreatorProfile(
                creator_id="high", type="wallet", display_name="High",
                first_seen="2026-01-01T00:00:00Z", reputation_score=0.8
            )
            agent.creator_profiles = {
                "low": low_rep,
                "high": high_rep
            }
            
            alpha_creators = agent.get_alpha_creators(min_score=0.5)
            assert len(alpha_creators) == 1
            assert alpha_creators[0].creator_id == "high"

    def test_update_reputation_calculation(self):
        """Test reputation score calculation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "creator_registry.json"
            agent = CreatorTrackerAgent({"creator_db_path": str(db_path)})
            
            profile = CreatorProfile(
                creator_id="test", type="wallet", display_name="Test",
                first_seen="2026-01-01T00:00:00Z",
                token_history=[
                    {"composite_score": 0.5},
                    {"composite_score": 0.7},
                    {"composite_score": 0.9}
                ],
                performance_metrics={},
                reputation_score=0.0
            )
            
            signal = {"composite_score": 0.8, "signal": "BUY"}
            agent._update_reputation(profile, signal)
            
            # _update_reputation uses existing token_history (3 items), not the signal
            # avg_score = (0.5+0.7+0.9)/3 = 0.7
            # reputation = 0.7 * sqrt(3) ≈ 1.21
            assert abs(profile.performance_metrics["avg_score"] - 0.7) < 0.001
            import math
            expected_reputation = 0.7 * math.sqrt(3)
            assert abs(profile.reputation_score - expected_reputation) < 0.01
