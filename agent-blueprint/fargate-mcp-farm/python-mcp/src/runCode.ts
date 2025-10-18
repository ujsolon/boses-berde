/* eslint @typescript-eslint/no-explicit-any: off */
import { loadPyodide } from 'pyodide'
import type { LoggingLevel } from '@modelcontextprotocol/sdk/types.js'

// Read the Python prepare_env.py file content
const preparePythonCode = await Deno.readTextFile(new URL('./prepare_env.py', import.meta.url))

export interface CodeFile {
  name: string
  content: string
  active: boolean
}

export async function runCode(
  files: CodeFile[],
  log: (level: LoggingLevel, data: string) => void,
): Promise<RunSuccess | RunError> {
  // remove once we can upgrade to pyodide 0.27.7 and console.log is no longer used.
  const realConsoleLog = console.log
  // deno-lint-ignore no-explicit-any
  console.log = (...args: any[]) => log('debug', args.join(' '))

  const output: string[] = []
  const pyodide = await loadPyodide({
    stdout: (msg) => {
      log('info', msg)
      output.push(msg)
    },
    stderr: (msg) => {
      log('warning', msg)
      output.push(msg)
    },
  })

  // see https://github.com/pyodide/pyodide/discussions/5512
  const origLoadPackage = pyodide.loadPackage
  pyodide.loadPackage = (pkgs, options) =>
    origLoadPackage(pkgs, {
      // stop pyodide printing to stdout/stderr
      messageCallback: (msg: string) => log('debug', `loadPackage: ${msg}`),
      errorCallback: (msg: string) => {
        log('error', `loadPackage: ${msg}`)
        output.push(`install error: ${msg}`)
      },
      ...options,
    })

  await pyodide.loadPackage(['micropip', 'pydantic'])
  const sys = pyodide.pyimport('sys')

  const dirPath = '/tmp/mcp_run_python'
  sys.path.append(dirPath)
  const pathlib = pyodide.pyimport('pathlib')
  pathlib.Path(dirPath).mkdir()
  const moduleName = '_prepare_env'

  pathlib.Path(`${dirPath}/${moduleName}.py`).write_text(preparePythonCode)

  const preparePyEnv: PreparePyEnv = pyodide.pyimport(moduleName)

  const prepareStatus = await preparePyEnv.prepare_env(pyodide.toPy(files))

  let runResult: RunSuccess | RunError
  if (prepareStatus.kind == 'error') {
    runResult = {
      status: 'install-error',
      output,
      error: prepareStatus.message,
    }
  } else {
    const { dependencies } = prepareStatus
    const activeFile = files.find((f) => f.active)! || files[0]
    try {
      const rawValue = await pyodide.runPythonAsync(activeFile.content, {
        globals: pyodide.toPy({ __name__: '__main__' }),
        filename: activeFile.name,
      })
      
      // Extract files created by Python code from Pyodide's virtual filesystem
      const generatedFiles = await extractPyodideFiles(pyodide)
      
      runResult = {
        status: 'success',
        dependencies,
        output,
        returnValueJson: preparePyEnv.dump_json(rawValue),
        generatedFiles, // Add generated files to result
      }
    } catch (err) {
      runResult = {
        status: 'run-error',
        dependencies,
        output,
        error: formatError(err),
      }
    }
  }
  sys.stdout.flush()
  sys.stderr.flush()
  console.log = realConsoleLog
  return runResult
}

/**
 * Extract files created by Python code from Pyodide's virtual filesystem
 */
async function extractPyodideFiles(pyodide: any): Promise<{ name: string; content: Uint8Array }[]> {
  const generatedFiles: { name: string; content: Uint8Array }[] = []
  
  try {
    // Use Python to list files in current directory and read their contents
    const listFilesCode = `
import os
import json

def list_generated_files():
    files_info = []
    current_dir = os.getcwd()
    
    for filename in os.listdir(current_dir):
        filepath = os.path.join(current_dir, filename)
        if os.path.isfile(filepath):
            # Skip Python files and common system files
            if filename.endswith('.py') or filename.startswith('.') or '__pycache__' in filename:
                continue
            
            try:
                # Try to read as binary data
                with open(filepath, 'rb') as f:
                    content = f.read()
                
                files_info.append({
                    'name': filename,
                    'size': len(content),
                    'content': list(content)  # Convert bytes to list for JSON serialization
                })
            except Exception as e:
                print(f"Error reading file {filename}: {e}")
    
    return json.dumps(files_info)

list_generated_files()
`
    
    const result = pyodide.runPython(listFilesCode)
    const filesInfo = JSON.parse(result)
    
    for (const fileInfo of filesInfo) {
      const content = new Uint8Array(fileInfo.content)
      generatedFiles.push({
        name: fileInfo.name,
        content: content
      })
    }
    
    console.log(`Extracted ${generatedFiles.length} files from Pyodide filesystem:`, generatedFiles.map(f => f.name))
    
  } catch (error) {
    console.warn('Error extracting files from Pyodide filesystem:', error)
  }
  
  return generatedFiles
}

interface RunSuccess {
  status: 'success'
  // we could record stdout and stderr separately, but I suspect simplicity is more important
  output: string[]
  dependencies: string[]
  returnValueJson: string | null
  generatedFiles?: { name: string; content: Uint8Array }[] // Files created by Python code
}

interface RunError {
  status: 'install-error' | 'run-error'
  output: string[]
  dependencies?: string[]
  error: string
}

export function asXml(runResult: RunSuccess | RunError): string {
  const xml = [`<status>${runResult.status}</status>`]
  if (runResult.dependencies?.length) {
    xml.push(
      `<dependencies>${JSON.stringify(runResult.dependencies)}</dependencies>`,
    )
  }
  if (runResult.output.length) {
    xml.push('<output>')
    const escapeXml = escapeClosing('output')
    xml.push(...runResult.output.map(escapeXml))
    xml.push('</output>')
  }
  if (runResult.status == 'success') {
    if (runResult.returnValueJson) {
      xml.push('<return_value>')
      xml.push(escapeClosing('return_value')(runResult.returnValueJson))
      xml.push('</return_value>')
    }
  } else {
    xml.push('<error>')
    xml.push(escapeClosing('error')(runResult.error))
    xml.push('</error>')
  }
  return xml.join('\n')
}

function escapeClosing(closingTag: string): (str: string) => string {
  const regex = new RegExp(`</?\\s*${closingTag}(?:.*?>)?`, 'gi')
  const onMatch = (match: string) => {
    return match.replace(/</g, '&lt;').replace(/>/g, '&gt;')
  }
  return (str) => str.replace(regex, onMatch)
}

// deno-lint-ignore no-explicit-any
function formatError(err: any): string {
  let errStr = err.toString()
  errStr = errStr.replace(/^PythonError: +/, '')
  // remove frames from inside pyodide
  errStr = errStr.replace(
    / {2}File "\/lib\/python\d+\.zip\/_pyodide\/.*\n {4}.*\n(?: {4,}\^+\n)?/g,
    '',
  )
  return errStr
}

interface PrepareSuccess {
  kind: 'success'
  dependencies: string[]
}
interface PrepareError {
  kind: 'error'
  message: string
}
interface PreparePyEnv {
  prepare_env: (files: CodeFile[]) => Promise<PrepareSuccess | PrepareError>
  // deno-lint-ignore no-explicit-any
  dump_json: (value: any) => string | null
}
