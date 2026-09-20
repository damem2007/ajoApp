'use strict';
// Requirements US-SCH-04: one vocabulary for contribution and collection frequency.
const AjoFrequencies=Object.freeze([
 {value:'daily',label:'Daily'},
 {value:'weekly',label:'Weekly'},
 {value:'bi-weekly',label:'Bi-weekly'},
 {value:'monthly',label:'Monthly'},
 {value:'bi-monthly',label:'Bi-monthly'},
 {value:'quarterly',label:'Quarterly'},
 {value:'semi-annual',label:'Semi-annual'},
 {value:'yearly',label:'Yearly'}
]);
if(typeof module!=='undefined')module.exports=AjoFrequencies;
