const range=n=>[...Array(n).keys()];
const C=(x,y,r,f,s)=>`<circle cx="${x}" cy="${y}" r="${r}" fill="${f}"${s?` stroke="${s}" stroke-width="1.5"`:""}/>`;
function art(p){
  const m=p.mat==="Sterling silver"?"#8e9ea4":"#bd8a2b", s=p.stone, v=p.v;
  const line=(d,w=2.5)=>`<path d="${d}" fill="none" stroke="${m}" stroke-width="${w}" stroke-linecap="round"/>`;
  const ring=(x,y,rx,ry,w)=>`<ellipse cx="${x}" cy="${y}" rx="${rx}" ry="${ry}" fill="none" stroke="${m}" stroke-width="${w}"/>`;
  let o="";
  if(p.cat==="Necklaces"){
    const pt=t=>[20+160*t, 30+(v===2?140:105)*4*t*(1-t)];
    o=line(`M20 30Q100 ${v===2?310:240} 180 30`);
    if(v===0) o+=range(15).map(i=>{const[x,y]=pt((i+1)/16);return C(x,y+3,3+4*Math.sin(Math.PI*(i+1)/16),s,m)}).join("");
    if(v===1){const[x,y]=pt(.5);o+=C(x,y+4,5,m)+`<path d="M100 ${y+8}q26 30 0 46q-26-16 0-46z" fill="${s}" stroke="${m}" stroke-width="4"/>`}
    if(v===2) o+=range(13).map(i=>{const[x,y]=pt((i+2)/16);return line(`M${x} ${y}v8`)+C(x,y+15,8,s,"#8a611a")+C(x,y+15,3,"#9c1f55")}).join("");
  }else if(p.cat==="Earrings"){
    for(const x of [58,142]){
      if(v===0) o+=C(x,55,11,s,m)+line(`M${x} 66v18`)+`<path d="M${x-32} 130C${x-30} 70 ${x+30} 70 ${x+32} 130Z" fill="${m}"/>`+range(7).map(i=>C(x-30+i*10,141,5,i%2?s:m)).join("")+C(x,108,5,s);
      if(v===1) o+=C(x,55,8,m)+line(`M${x} 60v62`)+C(x,140,20,s,m);
      if(v===2) o+=range(14).map(i=>C(x+30*Math.cos(i*Math.PI/7),105+30*Math.sin(i*Math.PI/7),5,m)).join("")+C(x,105,22,s,m)+C(x-7,97,5,"#ffffff88");
    }
  }else if(p.cat==="Bangles"){
    const hoops=v===1?[[85,90],[100,110],[115,130]]:v===0?[[78,85],[122,125]]:[[100,105]];
    for(const[x,y]of hoops){o+=ring(x,y,58,62,v===0?14:v===2?11:5);
      if(v!==1) o+=range(v===2?13:9).map(i=>{const a=Math.PI*(.1+.8*i/(v===2?12:8));return C(x+58*Math.cos(a),y+62*Math.sin(a),v===2?5:4,s)}).join("")}
  }else if(p.cat==="Rings"){
    o=ring(100,128,52,52,v===2?18:9);
    if(v===0) o+=line("M80 78L86 55M120 78L114 55",5)+`<path d="M72 58L86 40H114L128 58L100 86Z" fill="${s}" stroke="${m}" stroke-width="3"/>`;
    if(v===1) o+=range(6).map(i=>C(100+22*Math.cos(i*Math.PI/3),70+22*Math.sin(i*Math.PI/3),12,s,m)).join("")+C(100,70,11,"#f0cd83",m);
    if(v===2) o+=`<path d="M60 108a46 46 0 0 1 36-27" fill="none" stroke="#fff" stroke-width="4" opacity=".7"/>`;
  }else{
    for(const dy of [0,55]){o+=line(`M18 ${55+dy}Q100 ${125+dy} 182 ${55+dy}`);
      o+=range(11).map(i=>{const t=(i+1)/12,x=18+164*t,y=55+dy+140*t*(1-t);return v===0?line(`M${x} ${y}v10`,1.5)+C(x,y+16,6,m)+line(`M${x-3} ${y+18}h6`,1):C(x,y,i%2?3:6,i%2?m:s)}).join("")}
  }
  return `<svg class="art" viewBox="0 0 200 200" role="img" aria-label="Illustration of ${p.name}">${o}</svg>`;
}


document.querySelectorAll("[data-art]").forEach(el=>{
  const d=el.dataset;
  el.innerHTML=art({cat:d.cat,mat:d.mat,stone:d.stone,v:+d.v,name:d.name.replace(/[<>"&]/g,"")});
});

/* Hero garland */
(()=>{
  let o=`<path d="M-20 10Q600 330 1220 10" fill="none" stroke="#c99a3d" stroke-width="3"/>`;
  for(let i=1;i<24;i++){
    const t=i/24,x=-20+1240*t,y=10+640*t*(1-t),big=i===12,k=big?1.5:i%2?1:.55;
    const body=i%2||big?`<path d="M0 0v18" stroke="#c99a3d" stroke-width="2"/><path d="M-17 46C-16 12 16 12 17 46Z" fill="#c99a3d"/><circle cy="33" r="4" fill="#d8467f"/>`+[-14,-7,0,7,14].map(d=>`<circle cx="${d}" cy="52" r="3.5" fill="#f4f1e8"/>`).join(""):`<path d="M0 0v14" stroke="#c99a3d" stroke-width="2"/><circle cy="24" r="12" fill="#d8467f" stroke="#c99a3d" stroke-width="3"/>`;
    o+=`<g transform="translate(${x} ${y}) scale(${k})"><g class="drop" style="transform-origin:0 0;transform-box:fill-box;transform-origin:50% 0;animation-delay:${Math.abs(12-i)*45}ms">${body}</g></g>`;
  }
  const g=document.getElementById("garland");if(g)g.innerHTML=o;
})();

