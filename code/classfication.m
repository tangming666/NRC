net2=inceptionV3;
net1=RES;
layer = 'avg_pool'; 
path='C:\matlab\test0052\';
file = dir(path);
lengthFiles = length(file);
mean_x       =   mean(D,2);
ll           =   size(D,2);
err=0;
temp=0;
q=0;
 for i=1:7
    cloud_path=strcat(path,'\',file(i+2).name);
    cloud_img=dir(cloud_path);
    len=length(cloud_img)-2;
    for j=1:len 
        q=q+1;
        Img = imread(strcat(cloud_path,'\',cloud_img(j+2).name));
        disp(strcat(cloud_path,'\',cloud_img(j+2).name)); 
        trainingFeatures1 = activations(net1,Img,layer);
        trainingFeatures2 = activations(net2,Img,layer);
        t1=reshape(trainingFeatures1,2048,1);
        t2=reshape(trainingFeatures2,2048,1);
        y(1:2048,1)=t1;
        y(2049:4096,1)=t2;
        y=y(mid,1);
        y=double(y);
        [id, minerr] = RSC(D,D_labels,y,mean_x,ll);
        a=[cloud_img(j+2).name];
        lable=a(1:1);
        disp(['第',num2str(q),'张测试图片的标签值：',num2str(lable)]);
        disp(['第',num2str(q),'张测试图片的预测值：',num2str(id)]);
        disp(['预测失败数量',num2str(err)]);
        if(num2str(lable)==num2str(id))
            disp('预测成功');
            temp=temp+1;
        else
            disp('预测失败');
            err=err+1;
        end
    end
end
disp(['预测准确率为:',num2str(temp*100/3199),'%']);

