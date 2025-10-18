import json
import base64
import os
from typing import Dict, Any, List, Tuple

class StreamEventFormatter:
    """Handles formatting of streaming events for SSE"""
    
    @staticmethod
    def format_sse_event(event_data: dict) -> str:
        """Format event data as Server-Sent Event with proper JSON serialization"""
        try:
            return f"data: {json.dumps(event_data)}\n\n"
        except (TypeError, ValueError) as e:
            # Fallback for non-serializable objects
            return f"data: {json.dumps({'type': 'error', 'message': f'Serialization error: {str(e)}'})}\n\n"
    
    @staticmethod
    def extract_final_result_data(final_result) -> Tuple[List[Dict[str, str]], str]:
        """Extract images and text from final result with simplified logic"""
        images = []
        result_text = str(final_result)
        
        try:
            if hasattr(final_result, 'message') and hasattr(final_result.message, 'content'):
                content = final_result.message.content
                text_parts = []
                
                for item in content:
                    if isinstance(item, dict):
                        if "text" in item:
                            text_parts.append(item["text"])
                        elif "image" in item and "source" in item["image"]:
                            # Simple image extraction
                            image_data = item["image"]
                            images.append({
                                "format": image_data.get("format", "png"),
                                "data": image_data["source"].get("data", "")
                            })
                
                if text_parts:
                    result_text = " ".join(text_parts)
        
        except Exception as e:
            pass
        
        return images, result_text
    
    @staticmethod
    def create_init_event() -> str:
        """Create initialization event"""
        return StreamEventFormatter.format_sse_event({
            "type": "init",
            "message": "Initializing..."
        })
    
    @staticmethod
    def create_reasoning_event(reasoning_text: str) -> str:
        """Create reasoning event"""
        return StreamEventFormatter.format_sse_event({
            "type": "reasoning",
            "text": reasoning_text,
            "step": "thinking"
        })
    
    @staticmethod
    def create_response_event(text: str) -> str:
        """Create response event"""
        return StreamEventFormatter.format_sse_event({
            "type": "response",
            "text": text,
            "step": "answering"
        })
    
    @staticmethod
    def create_tool_use_event(tool_use: Dict[str, Any]) -> str:
        """Create tool use event"""
        return StreamEventFormatter.format_sse_event({
            "type": "tool_use",
            "toolUseId": tool_use.get("toolUseId"),
            "name": tool_use.get("name"),
            "input": tool_use.get("input", {})
        })
    
    @staticmethod
    def create_tool_result_event(tool_result: Dict[str, Any]) -> str:
        """Create tool result event - refactored for clarity"""
        # 1. Extract all content (text and images) and process Base64
        result_text, result_images = StreamEventFormatter._extract_all_content(tool_result)
        
        # 2. Handle storage based on tool type
        StreamEventFormatter._handle_tool_storage(tool_result, result_text)
        
        # 3. Build and return the event
        return StreamEventFormatter._build_tool_result_event(tool_result, result_text, result_images)
    
    @staticmethod
    def _extract_all_content(tool_result: Dict[str, Any]) -> Tuple[str, List[Dict[str, str]]]:
        """Extract text content and images from tool result and process Base64"""
        # Extract basic content from MCP format
        result_text, result_images = StreamEventFormatter._extract_basic_content(tool_result)
        
        # Process JSON content for screenshots and additional images
        json_images, cleaned_text = StreamEventFormatter._process_json_content(result_text)
        result_images.extend(json_images)
        
        # Process Base64 downloads for Python MCP tools
        final_text = StreamEventFormatter._process_base64_downloads(tool_result, cleaned_text)
        
        return final_text, result_images
    
    @staticmethod
    def _extract_basic_content(tool_result: Dict[str, Any]) -> Tuple[str, List[Dict[str, str]]]:
        """Extract basic text and image content from MCP format"""
        import base64
        
        result_text = ""
        result_images = []
        
        if "content" in tool_result:
            for item in tool_result["content"]:
                if isinstance(item, dict):
                    if "text" in item:
                        result_text += item["text"]
                    elif "image" in item and "source" in item["image"]:
                        image_source = item["image"]["source"]
                        image_data = ""
                        
                        if "data" in image_source:
                            image_data = image_source["data"]
                        elif "bytes" in image_source:
                            if isinstance(image_source["bytes"], bytes):
                                image_data = base64.b64encode(image_source["bytes"]).decode('utf-8')
                            else:
                                image_data = str(image_source["bytes"])
                        
                        if image_data:
                            result_images.append({
                                "format": item["image"].get("format", "png"),
                                "data": image_data
                            })
        
        return result_text, result_images
    
    @staticmethod
    def _process_json_content(result_text: str) -> Tuple[List[Dict[str, str]], str]:
        """Process JSON content to extract screenshots and clean text"""
        try:
            import json
            parsed_result = json.loads(result_text)
            extracted_images = StreamEventFormatter._extract_images_from_json_response(parsed_result)
            
            if extracted_images:
                cleaned_text = StreamEventFormatter._clean_result_text_for_display(result_text, parsed_result)
                return extracted_images, cleaned_text
            else:
                return [], result_text
                
        except (json.JSONDecodeError, TypeError):
            return [], result_text
    
    @staticmethod
    def _process_base64_downloads(tool_result: Dict[str, Any], result_text: str) -> str:
        """Process Base64 downloads for Python MCP tools"""
        tool_use_id = tool_result.get("toolUseId")
        if not tool_use_id:
            return result_text
            
        # Get tool info to check if this is a Python MCP tool
        tool_info = StreamEventFormatter._get_tool_info(tool_use_id)
        if not tool_info:
            return result_text
            
        tool_name = tool_info.get('tool_name')
        session_id = tool_info.get('session_id')
        
        # Only process for Python MCP tools
        if tool_name == 'run_python_code' and session_id:
            try:
                processed_text, file_info = StreamEventFormatter._handle_python_mcp_base64(
                    tool_use_id, result_text, session_id)
                if file_info:
                    print(f"📁 Intercepted and saved {len(file_info)} files for {tool_use_id}")
                    return processed_text
            except Exception as e:
                print(f"⚠️ Error processing Base64 downloads: {e}")
        
        return result_text
    
    @staticmethod
    def _build_tool_result_event(tool_result: Dict[str, Any], result_text: str, result_images: List[Dict[str, str]]) -> str:
        """Build the final tool result event"""
        tool_result_data = {
            "type": "tool_result",
            "toolUseId": tool_result.get("toolUseId"),
            "result": result_text
        }
        if result_images:
            tool_result_data["images"] = result_images
        
        return StreamEventFormatter.format_sse_event(tool_result_data)
    

    @staticmethod
    def _handle_tool_storage(tool_result: Dict[str, Any], result_text: str):
        """Handle storage based on tool type using handler pattern"""
        tool_use_id = tool_result.get("toolUseId")
        if not (tool_use_id and result_text):
            return
        
        try:
            handler = StreamEventFormatter._get_tool_handler(tool_use_id)
            handler.save(tool_use_id, result_text)
        except Exception as e:
            # Fallback error handling
            print(f"Warning: Storage error for {tool_use_id}: {e}")
            try:
                fallback_handler = StreamEventFormatter._get_fallback_handler(tool_use_id)
                fallback_handler.save(tool_use_id, result_text)
            except Exception as fallback_error:
                print(f"Warning: Fallback storage also failed for {tool_use_id}: {fallback_error}")
    
    @staticmethod
    def _get_tool_handler(tool_use_id: str):
        """Get appropriate handler for tool based on its type"""
        tool_info = StreamEventFormatter._get_tool_info(tool_use_id)
        
        if not tool_info:
            return StreamEventFormatter._DefaultToolHandler()
        
        tool_name = tool_info.get('tool_name')
        storage_behavior = StreamEventFormatter._get_tool_storage_behavior(tool_name)
        
        print(f"🔍 TOOL RESULT DEBUG: tool_use_id={tool_use_id}, tool_name={tool_name}")
        print(f"🔍 TOOL INFO: {tool_info}")
        
        if storage_behavior == 'self_managed':
            return StreamEventFormatter._SelfManagedToolHandler(tool_name)
        elif tool_name == 'run_python_code':
            session_id = tool_info.get('session_id')
            return StreamEventFormatter._PythonMCPToolHandler(tool_name, session_id)
        else:
            return StreamEventFormatter._DefaultToolHandler(tool_name)
    
    @staticmethod
    def _get_fallback_handler(tool_use_id: str):
        """Get fallback handler when primary handler fails"""
        try:
            tool_info = StreamEventFormatter._get_tool_info(tool_use_id)
            tool_name = tool_info.get('tool_name') if tool_info else 'unknown'
            storage_behavior = StreamEventFormatter._get_tool_storage_behavior(tool_name)
            
            if storage_behavior == 'self_managed':
                return StreamEventFormatter._SelfManagedToolHandler(tool_name)
            else:
                return StreamEventFormatter._DefaultToolHandler(tool_name)
        except:
            return StreamEventFormatter._DefaultToolHandler('unknown')
    
    @staticmethod
    def _get_tool_info(tool_use_id: str) -> Dict[str, Any]:
        """Get tool information from global processor"""
        try:
            from agent import get_global_stream_processor
            processor = get_global_stream_processor()
            if processor and hasattr(processor, 'tool_use_registry'):
                return processor.tool_use_registry.get(tool_use_id, {})
            return {}
        except Exception:
            return {}
    
    class _ToolHandler:
        """Base class for tool storage handlers"""
        def __init__(self, tool_name: str = 'unknown'):
            self.tool_name = tool_name
        
        def save(self, tool_use_id: str, result_text: str):
            raise NotImplementedError
    
    class _SelfManagedToolHandler(_ToolHandler):
        """Handler for tools that manage their own storage"""
        def save(self, tool_use_id: str, result_text: str):
            print(f"⏭️ Skipping auto-save for self-managed tool: {self.tool_name} ({tool_use_id})")
            # Intentionally do nothing - tool handles its own storage
    
    class _PythonMCPToolHandler(_ToolHandler):
        """Handler for Python MCP tools with special Base64 processing"""
        def __init__(self, tool_name: str, session_id: str = None):
            super().__init__(tool_name)
            self.session_id = session_id
        
        def save(self, tool_use_id: str, result_text: str):
            print(f"🎯 DETECTED PYTHON MCP TOOL: {self.tool_name}")
            # Base64 processing is now handled in _process_base64_downloads
            # Just save the result text (already processed)
            StreamEventFormatter._save_agent_tool_result(tool_use_id, result_text)
    
    class _DefaultToolHandler(_ToolHandler):
        """Default handler for regular tools"""
        def save(self, tool_use_id: str, result_text: str):
            print(f"🔍 DEFAULT TOOL: {self.tool_name} (tool_use_id: {tool_use_id})")
            StreamEventFormatter._save_agent_tool_result(tool_use_id, result_text)
    
    @staticmethod
    def create_complete_event(message: str, images: List[Dict[str, str]] = None) -> str:
        """Create completion event"""
        completion_data = {
            "type": "complete",
            "message": message
        }
        if images:
            completion_data["images"] = images
        
        return StreamEventFormatter.format_sse_event(completion_data)
    
    @staticmethod
    def create_error_event(error_message: str) -> str:
        """Create error event"""
        return StreamEventFormatter.format_sse_event({
            "type": "error",
            "message": error_message
        })
    
    @staticmethod
    def create_thinking_event(message: str = "Processing your request...") -> str:
        """Create thinking event"""
        return StreamEventFormatter.format_sse_event({
            "type": "thinking",
            "message": message
        })
    
    @staticmethod
    def create_progress_event(progress_data: Dict[str, Any]) -> str:
        """Create progress event for tool execution"""
        return StreamEventFormatter.format_sse_event({
            "type": "tool_progress",
            "toolId": progress_data.get("toolId"),
            "sessionId": progress_data.get("sessionId"),
            "step": progress_data.get("step"),
            "message": progress_data.get("message"),
            "progress": progress_data.get("progress"),
            "timestamp": progress_data.get("timestamp"),
            "metadata": progress_data.get("metadata", {})
        })
    
    

    @staticmethod
    def _handle_python_mcp_base64(tool_use_id: str, result_text: str, session_id: str) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Intercept Base64 file data from Python MCP results and save to local files
        Returns: (processed_text_without_base64, file_info_list)
        """
        import re
        import base64
        from config import Config
        
        file_info = []
        processed_text = result_text
        
        try:
            # Pattern to match Base64 data URLs: data:application/zip;base64,{base64_data}
            base64_pattern = r'<download>data:([^;]+);base64,([A-Za-z0-9+/=]+)</download>'
            
            # Check if pattern exists
            import re
            matches = re.findall(base64_pattern, result_text)
            
            def process_base64_match(match):
                mime_type = match.group(1)
                base64_data = match.group(2)
                
                try:
                    # Decode Base64 data
                    file_data = base64.b64decode(base64_data)
                    
                    # Determine file extension from MIME type
                    extension_map = {
                        'application/zip': '.zip',
                        'text/plain': '.txt',
                        'application/json': '.json',
                        'text/csv': '.csv',
                        'image/png': '.png',
                        'image/jpeg': '.jpg'
                    }
                    extension = extension_map.get(mime_type, '.bin')
                    
                    # Generate filename
                    filename = f"python_output_{len(file_info) + 1}{extension}"
                    
                    # Create output directory using provided session_id
                    if session_id:
                        try:
                            session_output_dir = Config.get_session_output_dir(session_id)
                            tool_dir = os.path.join(session_output_dir, tool_use_id)
                            os.makedirs(tool_dir, exist_ok=True)
                        except Exception as dir_error:
                            print(f"❌ Error creating directory: {dir_error}")
                            return match.group(0)
                        
                        # Save file
                        try:
                            file_path = os.path.join(tool_dir, filename)
                            with open(file_path, 'wb') as f:
                                f.write(file_data)
                            
                            # Create download URL (relative to session output)
                            relative_path = os.path.relpath(file_path, Config.get_output_dir())
                            download_url = f"/files/{relative_path}"
                            
                            file_info.append({
                                'filename': filename,
                                'mime_type': mime_type,
                                'size': len(file_data),
                                'download_url': download_url,
                                'local_path': file_path
                            })
                            
                            print(f"💾 Saved Base64 file: {filename} ({len(file_data)} bytes) -> {file_path}")
                            
                            # Replace Base64 data with simple message
                            return f"📁 Files have been saved as a ZIP archive."
                        except Exception as save_error:
                            print(f"❌ Error saving file: {save_error}")
                            return match.group(0)
                    else:
                        print(f"⚠️ No session ID found for tool_use_id: {tool_use_id}")
                        return match.group(0)  # Keep original if no session
                        
                except Exception as e:
                    print(f"❌ Error processing Base64 data: {e}")
                    return match.group(0)  # Keep original on error
            
            # Process all Base64 matches
            processed_text = re.sub(base64_pattern, process_base64_match, result_text)
            
            if file_info:
                print(f"💾 Processed Python MCP result: found {len(file_info)} files")
            
        except Exception as e:
            print(f"❌ Error in _handle_python_mcp_base64: {e}")
        
        return processed_text, file_info

    @staticmethod
    def _extract_images_from_json_response(response_data):
        """Extract images from any JSON tool response automatically"""
        images = []
        
        if isinstance(response_data, dict):
            # Support common image field patterns
            image_fields = ['screenshot', 'image', 'diagram', 'chart', 'visualization', 'figure']
            
            for field in image_fields:
                if field in response_data and isinstance(response_data[field], dict):
                    img_data = response_data[field]
                    
                    # Handle new lightweight screenshot format (Nova Act optimized)
                    if img_data.get("available") and "description" in img_data:
                        # This is the new optimized format - no actual image data
                        # Just skip extraction since there's no base64 data to process
                        print(f"📷 Found optimized screenshot reference: {img_data.get('description')}")
                        continue
                    
                    # Handle legacy format with actual base64 data
                    elif "data" in img_data and "format" in img_data:
                        images.append({
                            "format": img_data["format"],
                            "data": img_data["data"]
                        })
            
            # Preserve existing images array
            if "images" in response_data and isinstance(response_data["images"], list):
                images.extend(response_data["images"])
        
        return images

    @staticmethod
    def _clean_result_text_for_display(original_text: str, parsed_result: dict) -> str:
        """Clean result text by removing large image data but keeping other information"""
        try:
            import json
            import copy
            
            # Create a copy to avoid modifying the original
            cleaned_result = copy.deepcopy(parsed_result)
            
            # Remove large image data fields but keep metadata
            image_fields = ['screenshot', 'image', 'diagram', 'chart', 'visualization', 'figure']
            
            for field in image_fields:
                if field in cleaned_result and isinstance(cleaned_result[field], dict):
                    if "data" in cleaned_result[field]:
                        # Keep format and size info, remove the large base64 data
                        data_size = len(cleaned_result[field]["data"])
                        cleaned_result[field] = {
                            "format": cleaned_result[field].get("format", "unknown"),
                            "size": f"{data_size} characters",
                            "note": "Image data extracted and displayed separately"
                        }
            
            # Return the cleaned JSON string
            return json.dumps(cleaned_result, indent=2)
            
        except Exception as e:
            # If cleaning fails, return the original
            print(f"Warning: Failed to clean result text: {e}")
            return original_text

    @staticmethod
    def _get_tool_storage_behavior(tool_name: str) -> str:
        """Get storage behavior for a tool from config"""
        try:
            import json
            import os
            
            config_path = os.path.join(os.path.dirname(__file__), '..', 'unified_tools_config.json')
            
            if not os.path.exists(config_path):
                return 'default'
            
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # Find tool in config
            for tool in config.get('tools', []):
                if tool.get('id') == tool_name:
                    return tool.get('storage_behavior', 'default')
            
            return 'default'
            
        except Exception as e:
            print(f"Warning: Failed to get storage behavior for {tool_name}: {e}")
            return 'default'

    @staticmethod
    def _save_agent_tool_result(tool_use_id: str, result_text: str):
        """Save agent type tool result to memory store with chart replacement - only for actual agent tools"""
        try:
            from agent import get_global_stream_processor
            from config import Config
            from memory_store import get_memory_store
            import re
            
            processor = get_global_stream_processor()
            
            if not processor or not hasattr(processor, 'tool_use_registry'):
                return
                
            tool_info = processor.tool_use_registry.get(tool_use_id)
            if not tool_info:
                return
            
            tool_name = tool_info.get('tool_name')
            session_id = tool_info.get('session_id')
            
            if not tool_name or not session_id:
                return
            
            config_path = os.path.join(os.path.dirname(__file__), '..', 'unified_tools_config.json')
            
            if not os.path.exists(config_path):
                return
            
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            is_agent_tool = False
            for tool in config.get('tools', []):
                if tool.get('id') == tool_name and tool.get('tool_type') == 'agent':
                    is_agent_tool = True
                    break
            
            if is_agent_tool:
                # Get memory store to access chart data
                memory_store = get_memory_store()
                
                # Replace [CHART:chart_name:Title] with ```chart blocks
                def replace_chart_references(text):
                    # Pattern to match [CHART:chart_name:Title]
                    chart_pattern = r'\[CHART:([^:]+):([^\]]+)\]'
                    
                    def chart_replacer(match):
                        chart_name = match.group(1)
                        chart_title = match.group(2)
                        
                        # Get chart data from memory store
                        chart_data = memory_store.get_chart(session_id, chart_name)
                        
                        if chart_data:
                            # Convert chart data to ```chart block
                            chart_json = json.dumps(chart_data, indent=2)
                            return f"```chart\n{chart_json}\n```"
                        else:
                            # If chart not found, keep original reference
                            print(f"Warning: Chart '{chart_name}' not found in memory for session {session_id}")
                            return match.group(0)
                    
                    return re.sub(chart_pattern, chart_replacer, text)
                
                # Replace chart references in the result text
                processed_text = replace_chart_references(result_text)
                
                # Store processed text in memory
                metadata = {
                    'tool_name': tool_name,
                    'tool_type': 'agent'
                }
                memory_store.store_analysis(session_id, tool_use_id, processed_text, {}, metadata)
                
                print(f"Saved agent tool result to memory with chart replacement: session={session_id}, tool_use_id={tool_use_id}")
                
                # Also save to file for backward compatibility (optional)
                try:
                    session_output_dir = Config.get_session_output_dir(session_id)
                    tool_dir = os.path.join(session_output_dir, tool_name, tool_use_id)
                    os.makedirs(tool_dir, exist_ok=True)
                    
                    output_path = os.path.join(tool_dir, 'result.md')
                    with open(output_path, 'w', encoding='utf-8') as f:
                        f.write(processed_text)
                    
                    print(f"Also saved to file for compatibility: {output_path}")
                except Exception as file_error:
                    print(f"Warning: Failed to save file backup: {file_error}")
            
        except Exception as e:
            print(f"Warning: Failed to save agent tool result for {tool_use_id}: {e}")
    
