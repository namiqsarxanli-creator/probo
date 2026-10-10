'use strict';
const workspaceTabs=new Set(['soz','tender','team','review','policy','operations','trace']);
if(workspaceTabs.has(location.hash.slice(1))) location.replace('/workspace'+location.hash);
const video=document.getElementById('hero-video');
const toggle=document.getElementById('motion-toggle');
function syncMotion(){const paused=video.paused;toggle.textContent=paused?'▷ Motion-u başlat':'Ⅱ Motion-u dayandır';toggle.setAttribute('aria-pressed',String(paused));toggle.setAttribute('aria-label',paused?'Fon videosunu başlat':'Fon videosunu dayandır');}
video.muted=true;
const reduce=window.matchMedia('(prefers-reduced-motion: reduce)');
if(reduce.matches){video.autoplay=false;video.pause();}
else video.play().catch(syncMotion);
toggle.addEventListener('click',()=>{if(video.paused)video.play().catch(()=>{document.getElementById('video-notice').hidden=false;});else video.pause();});
video.addEventListener('play',syncMotion);video.addEventListener('pause',syncMotion);video.addEventListener('error',()=>{document.getElementById('video-notice').hidden=false;syncMotion();});
reduce.addEventListener('change',event=>{if(event.matches)video.pause();});
syncMotion();
