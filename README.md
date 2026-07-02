# agent-skills
[![skills.sh](https://skills.sh/b/DrOlu/agent-skills)](https://skills.sh/DrOlu/agent-skills)
A collection of open agent skills for the [skills.sh](https://skills.sh) ecosystem, installable with the open `skills` CLI.
## Install
```bash
# list all available skills
npx skills add DrOlu/agent-skills --list
# install a specific skill globally
npx skills add DrOlu/agent-skills --skill <name> -g -y
# install every skill
npx skills add DrOlu/agent-skills --skill '*' -g -y
```
## Skills (72)
| Skill | Description |
|-------|-------------|
| [`agent-browser`](./skills/agent-browser) | Automates browser interactions for web testing, form filling, screenshots, and data extraction. Use when the user needs to navigate websites, interact with w... |
| [`agent-creator`](./skills/agent-creator) | Create AiderDesk agent profiles via interactive Q&amp;A. |
| [`agentsecrets`](./skills/agentsecrets) | Zero-knowledge secrets infrastructure — AI agents manage the complete credential lifecycle without ever seeing values |
| [`agentspan`](./skills/agentspan) | Comprehensive Agentspan durable workflow orchestration skill for creating, running, scheduling, monitoring, and debugging AI agent workflows using the Agents... |
| [`animejs`](./skills/animejs) | Anime.js adapter patterns for HyperFrames. Use when writing Anime.js animations or timelines inside HyperFrames compositions, registering animations on windo... |
| [`av-whitelisting`](./skills/av-whitelisting) | Submit software to antivirus vendors to prevent false positive detections. Use when releasing new software that triggers AV warnings, submitting binaries for... |
| [`browser-use`](./skills/browser-use) | AI browser automation agent — navigate websites, fill forms, extract data, click elements, search the web, take screenshots, download files, and automate any... |
| [`casper`](./skills/casper) | Enterprise-grade autonomous penetration testing framework for comprehensive web application and API security assessment using CLI tools, specializing in auth... |
| [`casperpro`](./skills/casperpro) | Enterprise-grade penetration testing framework using curl + mitmproxy + playwright + python stack for comprehensive web application and API security assessme... |
| [`catalyst8000`](./skills/catalyst8000) | Comprehensive Cisco Catalyst 8000 SD-WAN engineering skill. Covers Catalyst 8000v (Cat8000v) edge router configuration, IOS XE SD-WAN CLI, vManage/vSmart/vBo... |
| [`ciscoxr`](./skills/ciscoxr) | Comprehensive Cisco IOS XR network engineering skill. Covers CLI configuration, command reference, BGP, OSPF, ISIS, MPLS, SR-MPLS, SRv6, EVPN, VRF, QoS, ACLs... |
| [`code-signing`](./skills/code-signing) | Sign Windows executables (.exe, .dll, .msi) and macOS applications (.app) with code signing certificates. Use when signing binaries for distribution, setting... |
| [`computer-use`](./skills/computer-use) | Use Orca&#x27;s computer-use CLI to inspect and control local desktop apps through accessibility trees, screenshots, and safe UI actions. Use when an agent n... |
| [`contribute-catalog`](./skills/contribute-catalog) | Author a new HyperFrames registry block (caption style, VFX block, transition, lower third) or component (text effect, overlay, snippet) and ship it as an up... |
| [`creatorskill`](./skills/creatorskill) | Create or update Pi prompt templates and Agent skills from a short user brief. Produces minimal, well-structured SKILL.md or prompt files that follow Agent S... |
| [`css-animations`](./skills/css-animations) | CSS animation adapter patterns for HyperFrames. Use when authoring CSS keyframes, animation-delay based timing, animation-fill-mode, animation-play-state, or... |
| [`dagu-workflows`](./skills/dagu-workflows) | Comprehensive Dagu workflow orchestration skill for creating, managing, and automating workflows with Dagu - a compact portable workflow engine. Covers all s... |
| [`data-analysis`](./skills/data-analysis) | Elite data analyst with advanced statistical expertise for comprehensive data quality assessment, exploratory analysis, hypothesis testing, time series forec... |
| [`dbcli`](./skills/dbcli) | Universal database CLI supporting 30+ databases (SQLite, PostgreSQL, MySQL, SQL Server, Oracle, MongoDB, ClickHouse, DuckDB and more). Execute SELECT/DDL/DML... |
| [`doc-coauthoring`](./skills/doc-coauthoring) | Guide users through a structured workflow for co-authoring documentation. Use when user wants to write documentation, proposals, technical specs, decision do... |
| [`docx`](./skills/docx) | Comprehensive document creation, editing, and analysis with support for tracked changes, comments, formatting preservation, and text extraction. When Claude ... |
| [`excel`](./skills/excel) | Comprehensive spreadsheet creation, editing, and analysis with support for formulas, formatting, data analysis, and visualization. When Claude needs to work ... |
| [`find-docs`](./skills/find-docs) | &gt;- |
| [`find-skills`](./skills/find-skills) | Helps users discover and install agent skills when they ask questions like &quot;how do I do X&quot;, &quot;find a skill for X&quot;, &quot;is there a skill ... |
| [`frontend-design`](./skills/frontend-design) | Create distinctive, production-grade frontend interfaces with high design quality. Use this skill when the user asks to build web components, pages, artifact... |
| [`gandalf-ctf`](./skills/gandalf-ctf) | &gt;- |
| [`goad`](./skills/goad) | GOAD (Game of Active Directory) lab environment — AWS-based Active Directory pentest lab with 1 Ubuntu jumpbox and 5 Windows Server VMs (2 forests, 3 domains... |
| [`gsap`](./skills/gsap) | GSAP animation reference for HyperFrames. Covers gsap.to(), from(), fromTo(), easing, stagger, defaults, timelines (gsap.timeline(), position parameter, labe... |
| [`hallmark`](./skills/hallmark) | Anti-AI-slop design skill for greenfield pages, audits, redesigns, and design extraction from URLs or screenshots. Use when the user asks to build a new app ... |
| [`himalaya`](./skills/himalaya) | CLI email client for IMAP and SMTP. Use when reading, searching, composing, sending, or managing email via terminal. Covers account setup, envelope listing, ... |
| [`hyperframes`](./skills/hyperframes) | Create video compositions, animations, title cards, overlays, captions, voiceovers, audio-reactive visuals, and scene transitions in HyperFrames HTML. Use wh... |
| [`hyperframes-cli`](./skills/hyperframes-cli) | HyperFrames CLI dev loop — `npx hyperframes` for scaffolding (init), validation (lint, inspect), preview, render, and environment troubleshooting (doctor, br... |
| [`hyperframes-media`](./skills/hyperframes-media) | Asset preprocessing for HyperFrames compositions — text-to-speech narration (Kokoro), audio/video transcription (Whisper), and background removal for transpa... |
| [`hyperframes-registry`](./skills/hyperframes-registry) | Install and wire registry blocks and components into HyperFrames compositions. Use when running hyperframes add, installing a block or component, wiring an i... |
| [`interminai`](./skills/interminai) | Control interactive terminal applications like vim, git rebase -i, git add -i, git add -p, apt, rclone config, sudo, w3m, and TUI apps. Can also supervise an... |
| [`large-file-reader`](./skills/large-file-reader) | Comprehensive toolkit for AI agents to read, analyze, and extract information from large files without overflowing context windows. Use when working with fil... |
| [`loop`](./skills/loop) | Run any task iteratively until completion using Ralph Wiggum methodology. Executes tasks in a persistent loop where the AI receives the same prompt repeatedl... |
| [`lottie`](./skills/lottie) | Lottie and dotLottie adapter patterns for HyperFrames. Use when embedding lottie-web JSON animations, .lottie files, @lottiefiles/dotlottie-web players, regi... |
| [`nylas`](./skills/nylas) | Nylas CLI for unified email, calendar, and contacts via IMAP/SMTP, Google, and Microsoft 365. Use when reading, searching, composing, sending, or managing em... |
| [`opencode-api`](./skills/opencode-api) | Remote system administration and shell execution through the OpenCode AI Server REST API for Windows, macOS, and Linux systems with full shell access, file o... |
| [`opencode-doc`](./skills/opencode-doc) | Comprehensive OpenCode documentation covering installation, configuration, providers, tools, agents, MCP servers, skills, plugins, SDK, and all features. Use... |
| [`orca-cli`](./skills/orca-cli) | &gt;- |
| [`orchestration`](./skills/orchestration) | &gt;- |
| [`paddleocr`](./skills/paddleocr) | Comprehensive PaddleOCR document intelligence skill covering OCR text extraction, table detection and QA, layout analysis, document-level reasoning, structur... |
| [`pdf`](./skills/pdf) | Comprehensive PDF manipulation toolkit for extracting text and tables, creating new PDFs, merging/splitting documents, and handling forms. When Claude needs ... |
| [`playwright-cli`](./skills/playwright-cli) | Automates browser interactions for web testing, form filling, screenshots, and data extraction. Use when the user needs to navigate websites, interact with w... |
| [`powerpoint`](./skills/powerpoint) | Presentation creation, editing, and analysis. When Claude needs to work with presentations (.pptx files) for: (1) Creating new presentations, (2) Modifying o... |
| [`pywinrm`](./skills/pywinrm) | Enterprise-grade Windows remote management skill using PyWinRM for connecting to any Windows server with WinRM enabled. Provides advanced system administrati... |
| [`reactorpro-doc`](./skills/reactorpro-doc) | Comprehensive ReactorPro documentation covering installation, features, agent mode, configuration, skills, MCP servers, and all capabilities. Use this skill ... |
| [`remotion-to-hyperframes`](./skills/remotion-to-hyperframes) | Translate an existing Remotion (React-based) video composition into a HyperFrames HTML composition. Use ONLY when the user explicitly asks to port, convert, ... |
| [`rpa`](./skills/rpa) | Enterprise-grade Robotic Process Automation framework for web automation without APIs - a UiPath alternative using Playwright, Python, mitmproxy, and open-so... |
| [`secure-scan`](./skills/secure-scan) | Comprehensive secure code analysis and vulnerability review using Semgrep, Gitleaks, Trivy, CodeQL, and Horusec in a layered defense approach. Covers secret ... |
| [`skill-creator`](./skills/skill-creator) | Design and create Agent Skills using progressive disclosure principles. Use when building new skills, planning skill architecture, or writing skill content. |
| [`supacode-cli`](./skills/supacode-cli) | Control Supacode from the terminal. Use when running Supacode CLI commands, managing worktrees, tabs, and surfaces programmatically, or when inside a Supacod... |
| [`superagent-cli`](./skills/superagent-cli) | Use the SuperAgent CLI to orchestrate worktrees, live terminals, and browser automation through a running SuperAgent editor. Use when an agent needs to creat... |
| [`tailwind`](./skills/tailwind) | Tailwind CSS v4.2 browser-runtime patterns for HyperFrames compositions. Use when scaffolding or editing projects created with `hyperframes init --tailwind`,... |
| [`temporal`](./skills/temporal) | Expert Temporal workflow specialist for creating, running, scheduling, monitoring, and debugging durable workflows using Python and uv. Covers activities, wo... |
| [`theme-factory`](./skills/theme-factory) | Step-by-step guide to add a new UI theme to AiderDesk (SCSS + CSS variables + types + i18n). |
| [`three`](./skills/three) | Three.js and WebGL adapter patterns for HyperFrames. Use when creating deterministic Three.js scenes, WebGL canvas layers, AnimationMixer timelines, camera m... |
| [`typegpu`](./skills/typegpu) | TypeGPU and raw WebGPU adapter patterns for HyperFrames. Use when creating GPU-rendered compositions with TypeGPU, raw WebGPU, WGSL fragment shaders, compute... |
| [`vapt`](./skills/vapt) | Comprehensive vulnerability assessment and penetration testing skill leveraging Secator, NetExec, Metasploit, and raw Python for advanced exploitation chaini... |
| [`video-creator`](./skills/video-creator) | Full-stack cinematic video production skill. Creates professional, story-driven 1920x1080 MP4 videos for products, services, events, SaaS, enterprises, and b... |
| [`waapi`](./skills/waapi) | Web Animations API adapter patterns for HyperFrames. Use when authoring element.animate() motion, Animation currentTime seeking, document.getAnimations(), Ke... |
| [`web-artifacts-builder`](./skills/web-artifacts-builder) | Suite of tools for creating elaborate, multi-component claude.ai HTML artifacts using modern frontend web technologies (React, Tailwind CSS, shadcn/ui). Use ... |
| [`webapp-testing`](./skills/webapp-testing) | Toolkit for interacting with and testing local web applications using Playwright. Supports verifying frontend functionality, debugging UI behavior, capturing... |
| [`website-to-hyperframes`](./skills/website-to-hyperframes) | \| |
| [`workflow`](./skills/workflow) | Create, run, schedule, monitor, and debug Temporal workflows using Python and uv. Expert in activities, workers, signals, queries, saga patterns, child workf... |
| [`writing-tests`](./skills/writing-tests) | Comprehensive guide for writing unit tests, integration tests, and component tests in AiderDesk using Vitest. Use when creating new tests, configuring mocks,... |
