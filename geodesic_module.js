// ============================================================
// HEMANTH GEODESIC EXPERIMENT — Christoffel Gate Angles (2026)
// CONFIDENTIAL — NOT FOR DISTRIBUTION
// Served only to authenticated admin users via /api/geodesic/module
// All content © Hemanth Gudaparthi 2026
// ============================================================
//
// Core idea (Hemanth notes pg 3):
//   "instead of ds use Gamma as theta"
//   Replace Rhyno et al. vj(lattice) with vj = sqrt(f(r))
//   derived directly from Christoffel symbols.
//   Test particle is QUANTUM ENTANGLED (EPR pair), not classical.
//   Every Trotter layer has DIFFERENT gate angles because r changes.
// ============================================================

(function(FORCES, BIT_ROLES) {

FORCES.geodesic = {
  color: '#1a6fa8',
  label: 'Hemanth Geodesic Experiment — Christoffel Gate Angles (2026)',
  desc: 'Hemanth key idea (notes pg 3): replace vj in Rhyno et al. with vj=sqrt(f(rj)) from the Christoffel symbol Gamma^r_tt=(GM/r^2)*f(r). The test particle is a quantum entangled EPR pair (not a classical mass). Each Trotter layer uses DIFFERENT gate angles because rj evolves with the geodesic. Set mode=0 for flat (all gates identical) vs mode=1 Schwarzschild (all gates distinct) to see the curvature encoding directly.',
  params: [
    { id:'kM',   name:'Black hole mass M', min:0.1, max:5.0,  step:0.1,  def:1.0,   unit:'M' },
    { id:'kr0',  name:'Init r / rs',       min:1.2, max:10.0, step:0.1,  def:3.0,   unit:'rs' },
    { id:'kdt',  name:'Trotter step dt',   min:0.02,max:0.3,  step:0.01, def:0.12,  unit:'t' },
    { id:'kD',   name:'Anisotropy Delta',  min:0.0, max:2.0,  step:0.05, def:0.5,   unit:'D' },
    { id:'kS',   name:'Trotter layers',    min:1,   max:12,   step:1,    def:6,     unit:'N' },
    { id:'kMode',name:'0=Flat 1=Schw',     min:0,   max:1,    step:1,    def:1,     unit:'mode' },
  ],
  _f:    function(r,rs) { return Math.max(1e-7, 1 - rs/r); },
  _rs:   function(M)    { return 2*M; },
  _vj:   function(r,rs) { return Math.sqrt(Math.max(1e-7, 1 - rs/r)); },
  _Grtt: function(r,M,rs) { return M/(r*r) * Math.max(1e-7, 1 - rs/r); },
  _Gtrt: function(r,M,rs) { return M/(r*r) / Math.max(1e-7, 1 - rs/r); },
  _th:   function(vj,D,dt) { return 2*dt*vj*D + Math.PI/2; },
  _ph:   function(vj,dt)   { return -2*dt*vj   - Math.PI/2; },
  getTheta: function(p) {
    var rs=this._rs(p.kM), r=p.kr0*rs;
    var vj = p.kMode>=0.5 ? this._vj(r,rs) : 1.0;
    return this._th(vj,p.kD,p.kdt);
  },
  _steps: function(p) {
    var rs=this._rs(p.kM), r0=p.kr0*rs;
    var dt=p.kdt, D=p.kD, S=Math.max(1,Math.round(p.kS));
    var schw=p.kMode>=0.5;
    var r=r0, vr=-0.15;
    var out=[];
    for(var s=0;s<S;s++){
      var vj   = schw ? this._vj(r,rs)      : 1.0;
      var Grtt = schw ? this._Grtt(r,p.kM,rs): 0.0;
      var Gtrt = schw ? this._Gtrt(r,p.kM,rs): 0.0;
      var th   = this._th(vj,D,dt);
      var ph   = this._ph(vj,dt);
      var tidal= schw ? Grtt*dt*0.5 : 0.0;
      var tdil = schw ? Gtrt*dt*0.3  : 0.0;
      out.push({s:s+1, r:r, fr:this._f(r,rs), vj:vj, Grtt:Grtt, Gtrt:Gtrt, th:th, ph:ph, tidal:tidal, tdil:tdil});
      if(schw){ vr+=(-Grtt)*dt; r+=vr*dt; r=Math.max(r,rs*1.01); }
    }
    return out;
  },
  gates: function(p) {
    var schw=p.kMode>=0.5;
    var steps=this._steps(p);
    var g=[];
    g.push({op:'H',  q:[0],   label:'H',    note:'test particle superpos.'});
    g.push({op:'CX', q:[0,1], label:'',      note:'EPR entangle particle+field'});
    g.push({op:'H',  q:[2],   label:'H',     note:'tidal ancilla'});
    g.push({op:'H',  q:[3],   label:'H',     note:'time-dil. register'});
    var show=Math.min(steps.length,3);
    for(var i=0;i<show;i++){
      var st=steps[i];
      var qa=i%2===0?0:1, qb=i%2===0?1:0;
      var tag=schw?'r='+st.r.toFixed(2):'flat';
      g.push({op:'RY',q:[qa],label:'RY\n('+st.ph.toFixed(3)+')',note:'phi step'+st.s+' '+tag});
      g.push({op:'RZ',q:[qa],label:'RZ\n('+st.th.toFixed(3)+')',note:'theta step'+st.s+' '+tag});
      g.push({op:'CX',q:[qa,qb],label:'',note:'Trotter even/odd '+st.s});
      if(schw && st.tidal>0.0005){
        g.push({op:'RZZ',q:[0,2],label:'RZZ\n('+st.tidal.toFixed(4)+')',note:'Gamma^r_tt s='+st.s});
      }
      if(schw && st.tdil>0.001){
        g.push({op:'RZ',q:[3],label:'RZ\n('+st.tdil.toFixed(4)+')',note:'Gamma^t_rt s='+st.s});
      }
    }
    g.push({op:'M',q:[0],label:'M',note:'particle exit'});
    g.push({op:'M',q:[1],label:'M',note:'EPR partner'});
    return g;
  },
  qasm: function(p, init) {
    var rs=this._rs(p.kM), r0=p.kr0*rs;
    var schw=p.kMode>=0.5;
    var steps=this._steps(p);
    var S=steps.length, D=p.kD, dt=p.kdt;
    var body='';
    for(var s=0;s<S;s++){
      var st=steps[s];
      var qa=s%2===0?0:1, qb=s%2===0?1:0;
      body+='\n// Trotter '+st.s+': r='+st.r.toFixed(4)+' f(r)='+st.fr.toFixed(5)+' vj='+st.vj.toFixed(5)+' Grtt='+st.Grtt.toFixed(5)+'\n';
      body+='// theta='+st.th.toFixed(6)+' phi='+st.ph.toFixed(6)+'  ('+(schw?'SCHWARZSCHILD: unique per layer':'FLAT: same every layer')+')\n';
      body+='ry('+st.ph.toFixed(6)+') q['+qa+'];\n';
      body+='rz('+st.th.toFixed(6)+') q['+qa+'];\n';
      body+='cx q['+qa+'], q['+qb+'];\n';
      if(schw && st.tidal>0.0005){
        body+='// Christoffel tidal Gamma^r_tt*dt/2='+st.tidal.toFixed(6)+'\n';
        body+='cx q[0], q[2];\nrz('+st.tidal.toFixed(6)+') q[2]; // tidal\ncx q[0], q[2];\n';
      }
      if(schw){
        body+='rz('+st.tdil.toFixed(6)+') q[3]; // Gamma^t_rt time dilation\n';
      }
    }
    var modeStr=schw?'SCHWARZSCHILD':'FLAT_SPACE';
    return '// Hemanth Gudaparthi Quantum Lab -- Geodesic '+modeStr+'\n' +
'// Hemanth note pg 3: "instead of ds use Gamma as theta"\n' +
'// vj = sqrt(1 - rs/r) per geodesic step (NOT fixed lattice)\n' +
'// M='+p.kM+' rs='+rs.toFixed(4)+' r0='+r0.toFixed(4)+' Delta='+D+' dt='+dt+' S='+S+'\n' +
'// Qubit roles:\n' +
'//   q[0] = test particle (quantum, entangled)\n' +
'//   q[1] = EPR field partner\n' +
'//   q[2] = Christoffel tidal ancilla (Gamma^r_tt)\n' +
'//   q[3] = time-dilation register (Gamma^t_rt)\n' +
'OPENQASM 2.0;\n' +
'include "qelib1.inc";\n' +
'qreg q[5];\n' +
'creg c[5];\n' +
'h q[0];       // test particle superposition\n' +
'cx q[0], q[1]; // EPR entangle: particle is quantum, not classical\n' +
'h q[2];        // tidal curvature register\n' +
'h q[3];        // time-dilation register\n' +
body +
'measure q[0] -> c[0];\n' +
'measure q[1] -> c[1];\n' +
'measure q[2] -> c[2];\n' +
'measure q[3] -> c[3];';
  },
  python: function(p) {
    var rs=this._rs(p.kM), r0=p.kr0*rs;
    var schw=p.kMode>=0.5;
    var steps=this._steps(p);
    var S=steps.length, D=p.kD, dt=p.kdt;
    var body='    qc.h(0)\n    qc.cx(0,1)\n    qc.h(2)\n    qc.h(3)\n';
    for(var s=0;s<S;s++){
      var st=steps[s];
      var qa=s%2===0?0:1, qb=s%2===0?1:0;
      body+='    # step '+st.s+': r='+st.r.toFixed(3)+' vj='+st.vj.toFixed(4)+' theta='+st.th.toFixed(5)+' phi='+st.ph.toFixed(5)+'\n';
      body+='    qc.ry('+st.ph.toFixed(6)+', '+qa+')\n';
      body+='    qc.rz('+st.th.toFixed(6)+', '+qa+')\n';
      body+='    qc.cx('+qa+', '+qb+')\n';
      if(schw && st.tidal>0.0005) body+='    qc.cx(0,2); qc.rz('+st.tidal.toFixed(6)+',2); qc.cx(0,2)\n';
      if(schw) body+='    qc.rz('+st.tdil.toFixed(6)+', 3)\n';
    }
    var modeStr=schw?'schwarzschild':'flat';
    return '#!/usr/bin/env python3\n' +
'# Hemanth Gudaparthi -- Geodesic '+modeStr.toUpperCase()+'\n' +
'# M='+p.kM+' rs='+rs.toFixed(4)+' r0='+r0.toFixed(4)+' Delta='+D+' dt='+dt+' S='+S+'\n' +
'# pip install qiskit qiskit-aer\n' +
'from qiskit import QuantumCircuit, transpile\n' +
'from qiskit_aer import AerSimulator\n\n' +
'def build():\n' +
'    qc = QuantumCircuit(5,5)\n' +
body +
'    qc.measure_all()\n' +
'    return qc\n\n' +
'def run(shots=4096):\n' +
'    qc=build(); print(qc.draw(\'text\'))\n' +
'    sim=AerSimulator()\n' +
'    job=sim.run(transpile(qc,sim,optimization_level=3),shots=shots)\n' +
'    counts=job.result().get_counts()\n' +
'    q0_zero=sum(v for k,v in counts.items() if list(k.replace(\' \',\'\'))[-1]==\'0\')\n' +
'    p_zero=q0_zero/shots\n' +
'    print(f"Mode: '+modeStr.toUpperCase()+'")\n' +
'    print(f"P(q0=0)={p_zero:.4f}  Deviation from 50%: {abs(p_zero-0.5):.4f}")\n' +
'    print("GEODESIC SIGNAL DETECTED" if abs(p_zero-0.5)>0.03 else "flat/baseline")\n' +
'    for k,v in sorted(counts.items(),key=lambda x:-x[1])[:6]:\n' +
'        print(f"  |{k}> {v:5d} ({v/shots*100:.1f}%) {\'|\'*int(v/shots*40)}")\n' +
'    return counts\n\n' +
'if __name__==\'__main__\': run()\n';
  },
  gateInfo: {
    title: 'Christoffel Gate: vj = sqrt(f(r))  — Hemanth 2026',
    body: 'Hemanth note page 3: "instead of ds use Gamma as theta". Standard approach (Rhyno et al.): vj = fixed lattice formula. Hemanth proposal: vj = sqrt(1-rs/r) where r evolves per the geodesic equation. This makes EVERY Trotter layer have a different gate angle. The test particle is an EPR entangled pair, not a classical mass. Gamma^r_tt = GM*f(r)/r^2 encodes radial curvature as RZZ tidal gates. Gamma^t_rt = GM/(r^2*f(r)) encodes time dilation as RZ phases on q[3] and DIVERGES as r approaches rs.',
    formula: 'vj = sqrt(1-rs/r)   theta = 2*dt*vj*Delta + pi/2   phi = -2*dt*vj - pi/2   Gamma^r_tt = GM*f(r)/r^2',
  },
  stateVec: function(p) {
    var rs=this._rs(p.kM), r=p.kr0*rs;
    var vj=p.kMode>=0.5 ? this._vj(r,rs) : 1.0;
    var th=this._th(vj,p.kD,p.kdt);
    var a=Math.cos(th/2), b=Math.sin(th/2);
    var ph=p.kMode>=0.5 ? this._Grtt(r,p.kM,rs)*p.kdt : 0;
    return {a:a, b:b, ph:ph};
  },
  limitations: [
    { title:'Geodesic uses coordinate time not proper time',
      type:'limit',
      body:'Trotter dt is coordinate time. Near horizon coordinate velocity dr/dt goes to 0 even as proper acceleration diverges. Full treatment needs affine parametrization.',
      fix:'Add 4-velocity normalization qc.rz(1/f(r)*dt, 3) to encode the constraint g_uv u^u u^v = -1 on the time-dilation register.'},
    { title:'No back-reaction of particle on metric',
      type:'limit',
      body:'Schwarzschild metric is fixed. A quantum particle with entanglement energy contributes T_uv = 2/sqrt(-g) * dSM/dg^uv. This feedback is not modeled.',
      fix:'Implement iterative update: after each Trotter step, update rs += Delta_E * G / c^4 where Delta_E is extracted from the entanglement entropy of q[0]-q[1].'},
    { title:'5 qubits cannot model full 4D angular degrees of freedom',
      type:'limit',
      body:'Gamma^theta_rtheta = 1/r and Gamma^phi_rphi = 1/r are omitted. These are important for circular orbits and photon sphere at r=1.5rs.',
      fix:'Add q[4] as angular momentum register with RZ(dt/r) per step. This enables photon sphere dynamics and orbital precession.'},
  ],
  experiments: [
    'Set mode=0 (flat): all gate angles identical, P(q0=0)~50%. Set mode=1 (Schw): all gates differ. Download both .qasm files and diff them.',
    'Set r0=1.1rs: Gamma^t_rt diverges, time-dilation register q[3] gets large RZ angles. P(q0=0) deviates strongly.',
    'Set Delta=0: pure XX model. Geodesic effect only from vj, no interaction. Compare with Delta=1 (isotropic Heisenberg).',
    'Set S=1 (single Trotter step) vs S=12: watch geodesic deviation accumulate over layers.',
    'Download Schwarzschild .py, run it, compare P(q0=0) for r0=10rs vs r0=1.2rs.',
  ],
};

// BIT_ROLES for geodesic (qubit interpretation table)
if (typeof BIT_ROLES !== 'undefined') {
  BIT_ROLES.geodesic = {
    qubits: [
      { q:'q[0]', role:'Quantum test particle (entangled)',
        zero:'Ground state — no Christoffel phase accumulated, flat geodesic',
        one:'Excited — Christoffel phase built up, geodesic deviated by curvature' },
      { q:'q[1]', role:'EPR partner / quantum field',
        zero:'Ground — no entanglement contribution to stress-energy',
        one:'Excited — entanglement energy non-zero, ER=EPR bridge active' },
      { q:'q[2]', role:'Christoffel tidal (Gamma^r_tt)',
        zero:'Weak tidal field — r >> rs',
        one:'Strong tidal — r near rs, Gamma^r_tt = GM*f(r)/r^2 growing' },
      { q:'q[3]', role:'Time-dilation (Gamma^t_rt)',
        zero:'Weak redshift — clocks near-normal rate',
        one:'Strong redshift — Gamma^t_rt = GM/(r^2*f(r)) diverging near horizon' },
    ],
    outcomes: [
      { bits:'|0000>', dom:true,  phys:'Flat-space baseline: particle undeviated. Dominant in flat mode.' },
      { bits:'|1000>', dom:false, phys:'Particle geodesic-deviated but weak tidal — moderate curvature region.' },
      { bits:'|1001>', dom:false, phys:'Particle deviated + time dilation — deeper into gravitational well.' },
      { bits:'|1011>', dom:false, phys:'Full geodesic deviation: particle deviated, EPR excited, tidal + time dilation — near horizon!' },
    ],
    stateNote:'KEY: compare P(q[0]=1) for flat mode vs Schwarzschild mode. Flat P stays near 50%. Schwarzschild deviates as Christoffel phases accumulate. Deviation grows as r0 approaches rs. Download both .qasm files — every line is numerically different in Schwarzschild mode. This is Hemanth novelty: vj = sqrt(f(r)) per geodesic step, not a fixed lattice.',
    formulaNote:'Geodesic signal = |P(q0=1,Schw) - P(q0=1,flat)|   vj=sqrt(1-rs/r)   Gamma^r_tt=GM*f(r)/r^2',
  };
}

})(window.FORCES, window.BIT_ROLES);
