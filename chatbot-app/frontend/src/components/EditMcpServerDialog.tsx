'use client';

import React, { useState, useEffect } from 'react';
import { Settings, Trash2, TestTube, CheckCircle, XCircle, Server } from 'lucide-react';
import { getApiUrl } from '@/config/environment';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from './ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from './ui/select';
import { Textarea } from './ui/textarea';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogTrigger,
} from './ui/dialog';

interface McpServer {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  connected?: boolean;
  tool_count?: number;
  type?: string;
  config?: {
    url: string;
  };
  category?: string;
  icon?: string;
}

interface EditMcpServerDialogProps {
  server: McpServer;
  onUpdateServer: (serverId: string, serverConfig: any) => Promise<void>;
  onDeleteServer: (serverId: string) => Promise<void>;
  trigger?: React.ReactNode;
}

export function EditMcpServerDialog({ 
  server, 
  onUpdateServer, 
  onDeleteServer,
  trigger 
}: EditMcpServerDialogProps) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{
    success: boolean;
    message: string;
    tools_count?: number;
    original_url?: string;
    resolved_url?: string;
    used_parameter_store?: boolean;
  } | null>(null);
  
  // Form state
  const [formData, setFormData] = useState({
    name: server.name,
    description: server.description,
    type: server.type || 'mcp',
    url: server.config?.url || '',
    category: server.category || 'general',
    icon: server.icon || 'server',
    enabled: server.enabled
  });

  // Reset form when server changes or dialog opens
  useEffect(() => {
    if (open) {
      setFormData({
        name: server.name,
        description: server.description,
        type: server.type || 'mcp',
        url: server.config?.url || '',
        category: server.category || 'general',
        icon: server.icon || 'server',
        enabled: server.enabled
      });
      setTestResult(null);
    }
  }, [server, open]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      const serverConfig = {
        id: server.id,
        name: formData.name,
        description: formData.description,
        type: formData.type,
        config: { url: formData.url },
        category: formData.category,
        icon: formData.icon,
        enabled: formData.enabled
      };

      await onUpdateServer(server.id, serverConfig);
      setOpen(false);
    } catch (error) {
      console.error('Failed to update server:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm(`Are you sure you want to delete "${server.name}"? This action cannot be undone.`)) {
      return;
    }
    
    setLoading(true);
    try {
      await onDeleteServer(server.id);
      setOpen(false);
    } catch (error) {
      console.error('Failed to delete server:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleTestConnection = async () => {
    if (!formData.url) {
      setTestResult({
        success: false,
        message: 'Please enter a server URL first'
      });
      return;
    }

    setTesting(true);
    setTestResult(null);

    try {
      const testConfig = {
        type: formData.type,
        config: { url: formData.url },
        headers: {}
      };

      const response = await fetch(getApiUrl('mcp/servers/test'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(testConfig),
      });

      const result = await response.json();
      setTestResult(result);
    } catch (error) {
      setTestResult({
        success: false,
        message: `Test failed: ${error instanceof Error ? error.message : 'Unknown error'}`
      });
    } finally {
      setTesting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {trigger || (
          <Button
            variant="ghost"
            size="sm"
            className="h-6 w-6 p-0 opacity-0 group-hover:opacity-100 transition-opacity"
          >
            <Settings className="h-3 w-3 text-gray-500" />
          </Button>
        )}
      </DialogTrigger>

      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Server className="h-5 w-5" />
            Edit MCP Server
          </DialogTitle>
          <DialogDescription>
            Modify server settings or remove the server configuration.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSave} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="name">Name *</Label>
            <Input
              id="name"
              value={formData.name}
              onChange={(e) => setFormData(prev => ({ ...prev, name: e.target.value }))}
              placeholder="My MCP Server"
              required
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="description">Description</Label>
            <Textarea
              id="description"
              value={formData.description}
              onChange={(e) => setFormData(prev => ({ ...prev, description: e.target.value }))}
              placeholder="Brief description of what this server provides"
              rows={2}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="category">Category</Label>
            <Select
              value={formData.category}
              onValueChange={(value) => setFormData(prev => ({ ...prev, category: value }))}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="general">General</SelectItem>
                <SelectItem value="development">Development</SelectItem>
                <SelectItem value="utilities">Utilities</SelectItem>
                <SelectItem value="remote">Remote</SelectItem>
                <SelectItem value="integration">Integration</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="url">Server URL *</Label>
            <Input
              id="url"
              value={formData.url}
              onChange={(e) => setFormData(prev => ({ ...prev, url: e.target.value }))}
              placeholder="https://your-mcp-server.com/mcp or ssm:///mcp/endpoints/serverless/my-server"
              required
            />
            <p className="text-xs text-muted-foreground">
              Use HTTP URLs ending with /mcp, or Parameter Store references like ssm:///mcp/endpoints/serverless/my-server
            </p>
          </div>

          <div className="border-t pt-4">
            <div className="flex items-center justify-between mb-2">
              <Label>Test Connection</Label>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleTestConnection}
                disabled={testing || !formData.url}
                className="flex items-center gap-2"
              >
                <TestTube className="h-4 w-4" />
                {testing ? 'Testing...' : 'Test'}
              </Button>
            </div>
            
            {testResult && (
              <div className={`p-3 rounded-md border ${
                testResult.success 
                  ? 'bg-green-50 border-green-200 text-green-800' 
                  : 'bg-red-50 border-red-200 text-red-800'
              }`}>
                <div className="flex items-center gap-2 mb-1">
                  {testResult.success ? (
                    <CheckCircle className="h-4 w-4 text-green-600" />
                  ) : (
                    <XCircle className="h-4 w-4 text-red-600" />
                  )}
                  <span className="font-medium text-sm">
                    {testResult.success ? 'Connection Successful' : 'Connection Failed'}
                  </span>
                </div>
                
                {/* Parameter Store information */}
                {testResult.used_parameter_store && (
                  <div className="text-xs mt-2 mb-2 p-2 bg-blue-50 border border-blue-200 rounded">
                    <div className="font-medium text-blue-800 mb-1">Parameter Store Resolution:</div>
                    <div className="text-blue-700">
                      <div><strong>Reference:</strong> {testResult.original_url}</div>
                      <div><strong>Resolved to:</strong> {testResult.resolved_url}</div>
                    </div>
                  </div>
                )}
                
                <p className="text-xs">{testResult.message}</p>
                {testResult.success && testResult.tools_count !== undefined && testResult.tools_count > 0 && (
                  <p className="text-xs mt-1">
                    Found {testResult.tools_count} tools available
                  </p>
                )}
              </div>
            )}
          </div>

          <DialogFooter className="flex justify-between">
            <Button
              type="button"
              variant="destructive"
              onClick={handleDelete}
              disabled={loading}
              className="flex items-center gap-2"
            >
              <Trash2 className="h-4 w-4" />
              {loading ? 'Deleting...' : 'Remove'}
            </Button>
            <div className="flex gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => setOpen(false)}
                disabled={loading}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={loading}>
                {loading ? 'Saving...' : 'Save'}
              </Button>
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
