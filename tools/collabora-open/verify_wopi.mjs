// SPDX-License-Identifier: MPL-2.0
// This Source Code Form is subject to the Mozilla Public License, v. 2.0.
// https://mozilla.org/MPL/2.0/
import http from 'node:http';
import fs from 'node:fs';
import crypto from 'node:crypto';
import {execFileSync} from 'node:child_process';
import path from 'node:path';

const [recipePath, sourceRoot, outputDirectory] = process.argv.slice(2);
const recipe = JSON.parse(fs.readFileSync(recipePath, 'utf8'));
const settings = recipe.verification;
const docker = (...args) => execFileSync('docker', args, {encoding: 'utf8'}).trim();
const gateway = JSON.parse(docker('network', 'inspect', 'bridge'))[0].IPAM.Config[0].Gateway;
const marker = crypto.randomUUID();
const accessToken = crypto.randomUUID();
const container = `${settings.container_prefix}-${crypto.randomUUID()}`;
let document = fs.readFileSync(path.join(sourceRoot, settings.document_fixture));
let saved = false;
let version = 1;
let socket;
const events = [];
const fixture = http.createServer(async (request, response) => {
  const url = new URL(request.url, 'http://fixture');
  if (url.searchParams.get('access_token') !== accessToken) {
    response.writeHead(401).end(); return;
  }
  if (request.method === 'GET' && url.pathname.endsWith('/contents')) {
    response.writeHead(200, {'Content-Type': 'application/octet-stream'}).end(document); return;
  }
  if (request.method === 'GET') {
    response.writeHead(200, {'Content-Type': 'application/json'}).end(JSON.stringify({
      BaseFileName: path.basename(settings.document_fixture), OwnerId: marker, UserId: marker,
      UserFriendlyName: 'Build verification', Size: document.length, Version: String(version),
      UserCanWrite: true, SupportsUpdate: true, SupportsLocks: false,
      LastModifiedTime: new Date().toISOString(), PostMessageOrigin: '*',
    })); return;
  }
  if (request.method === 'POST' && url.pathname.endsWith('/contents')) {
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    document = Buffer.concat(chunks); version += 1; saved = true;
    response.writeHead(200, {'Content-Type': 'application/json'}).end(JSON.stringify({LastModifiedTime: new Date().toISOString()}));
    return;
  }
  response.writeHead(200, {'Content-Type': 'application/json'}).end('{}');
});

await new Promise((resolve) => fixture.listen(0, gateway, resolve));
const origin = `http://${gateway}:${fixture.address().port}`;
try {
  docker('run', '-d', '--name', container,
    '-p', `127.0.0.1::${settings.container_port}`,
    ...settings.capabilities.flatMap((value) => ['--cap-add', value]),
    '-e', `aliasgroup1=${origin}`,
    '-e', `extra_params=${settings.server_arguments.join(' ')}`, recipe.docker.tag);
  const mapping = docker('port', container, String(settings.container_port)).split('\n')[0];
  const base = `http://${mapping}`;
  const deadline = Date.now() + settings.timeout_seconds * 1000;
  let discovery;
  while (Date.now() < deadline) {
    try { discovery = await fetch(`${base}/hosting/discovery`, {signal: AbortSignal.timeout(settings.request_timeout_ms)}); if (discovery.ok) break; } catch {}
    await new Promise((resolve) => setTimeout(resolve, settings.poll_interval_ms));
  }
  if (!discovery?.ok) throw new Error('Editor discovery did not become healthy');
  const wopi = `${origin}/wopi/files/${marker}?access_token=${accessToken}`;
  const wsUrl = `${base.replace('http:', 'ws:')}/cool/${encodeURIComponent(wopi)}/ws?WOPISrc=${encodeURIComponent(wopi)}`;
  socket = new WebSocket(wsUrl);
  await new Promise((resolve, reject) => {
    socket.addEventListener('open', resolve, {once: true});
    socket.addEventListener('error', reject, {once: true});
  });
  let loaded = false;
  socket.addEventListener('message', async (event) => {
    const text = typeof event.data === 'string' ? event.data : await event.data.text();
    events.push(text.slice(0, settings.max_recorded_message_characters));
    if (!loaded && text.startsWith('status:')) {
      loaded = true;
      socket.send(`paste mimetype=text/plain\n${marker}`);
      socket.send('save dontTerminateEdit=0 dontSaveIfUnmodified=0');
    }
  });
  socket.send('coolclient 0.1');
  socket.send(`load url=${encodeURIComponent(wopi)} lang=${settings.language}`);
  while (!saved && Date.now() < deadline) await new Promise((resolve) => setTimeout(resolve, settings.poll_interval_ms));
  if (!saved) throw new Error('No WOPI PutFile after editing: ' + events.join('\n'));
  fs.mkdirSync(outputDirectory, {recursive: true});
  const savedFile = path.join(outputDirectory, path.basename(settings.document_fixture));
  fs.writeFileSync(savedFile, document);
  // A real saved DOCX must contain the inserted text, not merely issue PutFile.
  execFileSync('python3', ['-c', 'import sys,zipfile; z=zipfile.ZipFile(sys.argv[1]); assert sys.argv[2] in z.read("word/document.xml").decode()', savedFile, marker]);
  const result = {image: recipe.docker.tag, discovery: true, loaded, saved, inserted_text_verified: true,
    saved_bytes: document.length, saved_sha256: crypto.createHash('sha256').update(document).digest('hex')};
  fs.writeFileSync(path.join(outputDirectory, settings.result_file), JSON.stringify(result, null, 2) + '\n');
  console.log(JSON.stringify(result));
} catch (error) {
  try { console.error(docker('logs', '--tail', String(settings.failure_log_lines), container)); } catch {}
  throw error;
} finally {
  socket?.close();
  fixture.close();
  try { docker('rm', '-f', container); } catch {}
}
