"""
Tests for the file_server module.

Tests HTTP handlers and response generation.
"""

import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock
import json

# Skip if aiohttp not available
pytest.importorskip("aiohttp")

from src.file_server import (
    list_files,
    api_files,
    RESULTS_DIR,
    PORT,
)


class TestConstants:
    """Tests for module constants."""
    
    def test_results_dir_path(self):
        """Test results directory path."""
        assert RESULTS_DIR == Path("/app/data/compare_results")
    
    def test_port_number(self):
        """Test port number."""
        assert PORT == 8080


class TestListFiles:
    """Tests for list_files handler."""
    
    @pytest.fixture
    def mock_request(self):
        """Create a mock request."""
        return MagicMock()
    
    @pytest.mark.asyncio
    async def test_list_files_returns_html(self, mock_request):
        """Test that list_files returns HTML response."""
        with patch.object(Path, 'mkdir'):
            with patch.object(Path, 'glob', return_value=[]):
                response = await list_files(mock_request)
        
        assert response.content_type == "text/html"
    
    @pytest.mark.asyncio
    async def test_list_files_contains_title(self, mock_request):
        """Test that response contains title."""
        with patch.object(Path, 'mkdir'):
            with patch.object(Path, 'glob', return_value=[]):
                response = await list_files(mock_request)
        
        assert "Compare Results" in response.text
    
    @pytest.mark.asyncio
    async def test_list_files_with_files(self, mock_request):
        """Test list_files with existing files."""
        # Create mock file
        mock_file = MagicMock(spec=Path)
        mock_file.name = "test_2024-01-01.json"
        mock_stat = MagicMock()
        mock_stat.st_size = 1024
        mock_stat.st_mtime = datetime.now().timestamp()
        mock_file.stat.return_value = mock_stat
        
        with patch.object(Path, 'mkdir'):
            with patch.object(Path, 'glob', return_value=[mock_file]):
                response = await list_files(mock_request)
        
        assert "test_2024-01-01.json" in response.text
    
    @pytest.mark.asyncio
    async def test_list_files_creates_directory(self, mock_request):
        """Test that directory is created if missing."""
        with patch.object(Path, 'mkdir') as mock_mkdir:
            with patch.object(Path, 'glob', return_value=[]):
                await list_files(mock_request)
        
        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)


class TestApiFiles:
    """Tests for api_files handler."""
    
    @pytest.fixture
    def mock_request(self):
        """Create a mock request with host."""
        request = MagicMock()
        request.host = "localhost:8080"
        return request
    
    @pytest.mark.asyncio
    async def test_api_files_returns_json(self, mock_request):
        """Test that api_files returns JSON response."""
        with patch.object(Path, 'mkdir'):
            with patch.object(Path, 'glob', return_value=[]):
                response = await api_files(mock_request)
        
        assert response.content_type == "application/json"
    
    @pytest.mark.asyncio
    async def test_api_files_empty_response(self, mock_request):
        """Test api_files with no files."""
        with patch.object(Path, 'mkdir'):
            with patch.object(Path, 'glob', return_value=[]):
                response = await api_files(mock_request)
        
        data = json.loads(response.text)
        assert data["files"] == []
        assert data["count"] == 0
    
    @pytest.mark.asyncio
    async def test_api_files_with_files(self, mock_request):
        """Test api_files with existing files."""
        mock_file = MagicMock(spec=Path)
        mock_file.name = "result_2024.json"
        mock_stat = MagicMock()
        mock_stat.st_size = 2048
        mock_stat.st_mtime = datetime.now().timestamp()
        mock_file.stat.return_value = mock_stat
        
        with patch.object(Path, 'mkdir'):
            with patch.object(Path, 'glob', return_value=[mock_file]):
                response = await api_files(mock_request)
        
        data = json.loads(response.text)
        assert len(data["files"]) == 1
        assert data["count"] == 1
        assert data["files"][0]["name"] == "result_2024.json"
        assert data["files"][0]["size"] == 2048
    
    @pytest.mark.asyncio
    async def test_api_files_url_format(self, mock_request):
        """Test that file URLs are formatted correctly."""
        mock_file = MagicMock(spec=Path)
        mock_file.name = "test.json"
        mock_stat = MagicMock()
        mock_stat.st_size = 100
        mock_stat.st_mtime = datetime.now().timestamp()
        mock_file.stat.return_value = mock_stat
        
        with patch.object(Path, 'mkdir'):
            with patch.object(Path, 'glob', return_value=[mock_file]):
                response = await api_files(mock_request)
        
        data = json.loads(response.text)
        assert "http://localhost:8080/test.json" in data["files"][0]["url"]
    
    @pytest.mark.asyncio
    async def test_api_files_creates_directory(self, mock_request):
        """Test that directory is created if missing."""
        with patch.object(Path, 'mkdir') as mock_mkdir:
            with patch.object(Path, 'glob', return_value=[]):
                await api_files(mock_request)
        
        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)


class TestFileMetadata:
    """Tests for file metadata extraction."""
    
    @pytest.fixture
    def mock_request(self):
        request = MagicMock()
        request.host = "localhost:8080"
        return request
    
    @pytest.mark.asyncio
    async def test_file_size_extraction(self, mock_request):
        """Test that file size is correctly extracted."""
        mock_file = MagicMock(spec=Path)
        mock_file.name = "test.json"
        mock_stat = MagicMock()
        mock_stat.st_size = 12345
        mock_stat.st_mtime = datetime.now().timestamp()
        mock_file.stat.return_value = mock_stat
        
        with patch.object(Path, 'mkdir'):
            with patch.object(Path, 'glob', return_value=[mock_file]):
                response = await api_files(mock_request)
        
        data = json.loads(response.text)
        assert data["files"][0]["size"] == 12345
    
    @pytest.mark.asyncio
    async def test_file_modified_time(self, mock_request):
        """Test that modification time is extracted."""
        mock_file = MagicMock(spec=Path)
        mock_file.name = "test.json"
        mock_stat = MagicMock()
        mock_stat.st_size = 100
        # Use a specific timestamp
        test_time = datetime(2024, 1, 15, 12, 0, 0).timestamp()
        mock_stat.st_mtime = test_time
        mock_file.stat.return_value = mock_stat
        
        with patch.object(Path, 'mkdir'):
            with patch.object(Path, 'glob', return_value=[mock_file]):
                response = await api_files(mock_request)
        
        data = json.loads(response.text)
        # Should be ISO format date
        assert "2024-01-15" in data["files"][0]["modified"]


class TestHtmlOutput:
    """Tests for HTML output formatting."""
    
    @pytest.fixture
    def mock_request(self):
        return MagicMock()
    
    @pytest.mark.asyncio
    async def test_html_contains_table(self, mock_request):
        """Test that HTML contains a table."""
        with patch.object(Path, 'mkdir'):
            with patch.object(Path, 'glob', return_value=[]):
                response = await list_files(mock_request)
        
        assert "<table>" in response.text
        assert "</table>" in response.text
    
    @pytest.mark.asyncio
    async def test_html_contains_latest_link(self, mock_request):
        """Test that HTML contains latest.json link."""
        with patch.object(Path, 'mkdir'):
            with patch.object(Path, 'glob', return_value=[]):
                response = await list_files(mock_request)
        
        assert "latest.json" in response.text
    
    @pytest.mark.asyncio
    async def test_html_contains_api_link(self, mock_request):
        """Test that HTML contains API endpoint link."""
        with patch.object(Path, 'mkdir'):
            with patch.object(Path, 'glob', return_value=[]):
                response = await list_files(mock_request)
        
        assert "/api/files" in response.text
    
    @pytest.mark.asyncio
    async def test_html_styling(self, mock_request):
        """Test that HTML includes CSS styling."""
        with patch.object(Path, 'mkdir'):
            with patch.object(Path, 'glob', return_value=[]):
                response = await list_files(mock_request)
        
        assert "<style>" in response.text
        assert "font-family" in response.text


class TestMultipleFiles:
    """Tests for handling multiple files."""
    
    @pytest.fixture
    def mock_request(self):
        request = MagicMock()
        request.host = "localhost:8080"
        return request
    
    @pytest.mark.asyncio
    async def test_multiple_files_count(self, mock_request):
        """Test api_files with multiple files."""
        files = []
        for i in range(5):
            mock_file = MagicMock(spec=Path)
            mock_file.name = f"result_{i}.json"
            mock_stat = MagicMock()
            mock_stat.st_size = 100 * (i + 1)
            mock_stat.st_mtime = datetime.now().timestamp()
            mock_file.stat.return_value = mock_stat
            files.append(mock_file)
        
        with patch.object(Path, 'mkdir'):
            with patch.object(Path, 'glob', return_value=files):
                response = await api_files(mock_request)
        
        data = json.loads(response.text)
        assert data["count"] == 5
        assert len(data["files"]) == 5
